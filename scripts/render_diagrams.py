#!/usr/bin/env python3
"""Validate a source-grounded graph specification and render two interactive views."""
import argparse
import copy
import html
import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote, urlparse
from xml.etree import ElementTree as ET

from source_inventory import Source

COLORS = {'base': ('#e8f1ff', '#5073a5'), 'on': ('#e3f5e9', '#308154'),
          'off': ('#fff0d8', '#b67c24'), 'train': ('#f0e7fa', '#8654a4'),
          'cot': ('#fde7ee', '#a84f70'), 'note': ('#fffbdc', '#a68b29'),
          'out': ('#dbf4f5', '#287c88'), 'rl': ('#e8e5ff', '#6d5da7')}
RELATIONS = {'data': '前向数据', 'control': '控制依赖', 'sequence': '执行顺序（无张量传递）',
             'condition': '条件分支', 'state': '跨帧状态', 'annotation': '说明（非计算/调度）'}
VIEWS = {'full', 'inference'}
LEGEND = ('蓝：常规计算；绿：可选开启；橙：可选关闭；粉：语言/迭代\n'
          '青：输出；紫：训练；黄：事实/限制\n'
          '实线：数据/控制；红粗实线：执行顺序\n'
          '橙虚线：条件；绿虚线：跨帧；紫点线：说明')


def require(test, message):
    if not test:
        raise ValueError(message)


def validate(spec, src):
    require(spec.get('schema_version') == 1, 'Expected schema_version=1')
    for field in ('title', 'source', 'profile', 'configs', 'symbols', 'switches', 'verification', 'clusters', 'nodes', 'edges'):
        require(field in spec, 'Missing ' + field)
    require(spec['verification'], 'Describe actual verification and limitations')
    require(spec['nodes'], 'Empty graph')
    for path in spec['configs']:
        src.read(path)
    unknown = []
    counts = {'derived': 0, 'observed': 0, 'unknown': 0}
    base_url = spec['source'].get('url', '').rstrip('/')
    if base_url:
        require(urlparse(base_url).scheme in ('https', 'http'), 'Source URL must be HTTP(S)')

    def refs(items):
        require(isinstance(items, list) and items, 'Source references are required')
        for ref in items:
            data = src.read(ref['path'])
            line = ref.get('line')
            end = ref.get('end_line', line)
            require(isinstance(line, int) and isinstance(end, int) and 1 <= line <= end <= len(data.splitlines()),
                    'Invalid source line: ' + str(ref))
            ref.pop('url', None)
            if base_url and src.revision:
                ref['url'] = base_url + '/blob/' + src.revision + '/' + quote(ref['path'], safe='/') + '#L' + str(line)

    def views(item, where):
        v = item.get('views')
        require(isinstance(v, list) and v and set(v) <= VIEWS, 'Invalid views: ' + where)

    for key, n in spec['nodes'].items():
        require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key) is not None, 'Invalid node ID ' + key)
        require(not key.startswith('skillmeta_'), 'Reserved node prefix skillmeta_')
        for field in ('title', 'body', 'cluster', 'kind', 'inputs', 'outputs', 'source_refs'):
            require(field in n, key + ': missing ' + field)
        require(n['cluster'] in spec['clusters'] and n['kind'] in COLORS, 'Invalid cluster/kind: ' + key)
        views(n, key)
        require(not (n['kind'] in ('train', 'rl') and 'inference' in n['views']), 'Training node in inference: ' + key)
        refs(n['source_refs'])
        n['id'] = 'node_' + key
        for side in ('inputs', 'outputs'):
            names = set()
            for p in n[side]:
                for field in ('name', 'shape', 'axes', 'dtype', 'basis', 'status'):
                    require(isinstance(p.get(field), str) and p[field].strip(), key + ': invalid port ' + field)
                require(p['name'] not in names, key + ': duplicate port ' + p['name'])
                names.add(p['name'])
                require(p['status'] in counts, key + ': invalid shape status')
                require('?' not in p['shape'] or p['status'] == 'unknown', key + ': ? shape must be unknown')
                counts[p['status']] += 1
                if p['status'] == 'unknown':
                    unknown.append(dict(node=key, side=side, **p))
        port_text = []
        for side, label in (('inputs', '输入'), ('outputs', '输出')):
            for p in n[side]:
                port_text.append(f"{label} {p['name']}: {p['shape']} · {p['dtype']}\n轴：{p['axes']}；{p['status']}：{p['basis']}")
        n['body'] += ('\n' + '\n'.join(port_text)) if port_text else ''

    for i, e in enumerate(spec['edges'], 1):
        require(e.get('source') in spec['nodes'] and e.get('target') in spec['nodes'], 'Edge endpoint missing')
        require(e.get('kind') in RELATIONS and e.get('meaning'), 'Edge kind/meaning missing')
        views(e, 'edge ' + str(i))
        before, after = (spec['nodes'][e[k]] for k in ('source', 'target'))
        require(set(e['views']) <= set(before['views']) & set(after['views']), 'Edge view incompatible with endpoints')
        if e['kind'] == 'data':
            require(before['kind'] != 'off' and after['kind'] != 'off', 'Disabled branch cannot have active data edges')
            outputs = {p['name']: p for p in before['outputs']}
            inputs = {p['name']: p for p in after['inputs']}
            require(e.get('source_port') in outputs and e.get('target_port') in inputs, 'Data edge must bind real ports')
            a, b = outputs[e['source_port']], inputs[e['target_port']]
            require(re.sub(r'\s', '', a['shape']) == re.sub(r'\s', '', b['shape']), 'Shape mismatch on ' + str(i))
            require(a['dtype'] == b['dtype'], 'Dtype mismatch; add explicit cast node on ' + str(i))
            e['label'] = e.get('label') or f"{a['name']} {a['shape']}"
        elif e['kind'] == 'sequence':
            e['label'] = '顺序：' + e.get('label', '前一操作返回后执行')
        elif e['kind'] in ('condition', 'state'):
            require(e.get('label'), 'Condition/state edge requires condition/time label')
        e.setdefault('label', '')
        e['id'] = f'wire_{i:03d}'
        e['relation'] = RELATIONS[e['kind']]
        if e.get('source_refs'):
            refs(e['source_refs'])
        else:
            e['source_refs'] = before['source_refs'] + after['source_refs']
    for view in VIEWS:
        require(any(view in n['views'] for n in spec['nodes'].values()), 'Empty view ' + view)
    return dict(port_counts=counts, unknown_ports=unknown, verification=spec['verification'],
                note='Checks validate specification consistency and source bytes, not model execution or mathematical correctness.')


def metadata_nodes(spec, src):
    provenance = ('固定提交 ' + src.revision) if src.revision else '实际工作区字节（详见 source_audit.json）'
    switches = '\n'.join(str(s['name']) + '=' + json.dumps(s['value'], ensure_ascii=False) +
                         '；默认=' + json.dumps(s.get('default', '未声明'), ensure_ascii=False) +
                         '；' + s['effect'] for s in spec['switches'])
    bodies = [('scope', '源码版本与配置', provenance + '\n' + spec['profile'] + '\n配置：' + ', '.join(spec['configs'])),
              ('legend', '颜色与线条语义', LEGEND),
              ('symbols', '维度符号与开关', '\n'.join(k + ': ' + v for k, v in spec['symbols'].items()) + '\n' + switches),
              ('verification', '验证范围与限制', '\n'.join(spec['verification']))]
    return {('skillmeta_' + k): dict(id='node_skillmeta_' + k, title=t, body=b, cluster='skillmeta',
                                   kind='note', source_refs=[]) for k, t, b in bodies}


def render(spec, src, view, output, font):
    output.mkdir(parents=True, exist_ok=True)
    nodes = {k: n for k, n in spec['nodes'].items() if view in n['views']}
    nodes.update(metadata_nodes(spec, src))
    edges = [e for e in spec['edges'] if view in e['views']]
    clusters = {'skillmeta': '版本、配置与图例', **spec['clusters']}
    title = spec['title'] + (' · 完整训练与推理结构' if view == 'full' else ' · 纯推理结构')
    q = lambda s: json.dumps(s, ensure_ascii=False)
    lines = ['digraph Architecture {',
             'graph [rankdir=LR, compound=true, bgcolor="#f8fafc", pad=0.45, nodesep=0.32, ranksep=0.7, splines=polyline, labelloc=t, fontsize=26, fontname=' + q(font) + ',label=' + q(title + '\n' + spec['profile']) + '];',
             'node [shape=box, style="rounded,filled", fontsize=13, margin="0.16,0.12", fontname=' + q(font) + '];',
             'edge [fontsize=10, arrowsize=0.65, color="#63768b", fontname=' + q(font) + '];']
    for i, (cluster, label) in enumerate(clusters.items()):
        members = [(k, n) for k, n in nodes.items() if n['cluster'] == cluster]
        if not members:
            continue
        lines.append('subgraph cluster_' + str(i) + ' { label=' + q(label) + ';style=rounded;color="#cbd5e1";')
        for key, n in members:
            fill, border = COLORS[n['kind']]
            style = 'rounded,filled,dashed' if n['kind'] == 'off' else 'rounded,filled'
            lines.append(q(key) + ' [id=' + q(n['id']) + ',label=' + q(n['title'] + '\n' + n['body']) +
                         ',fillcolor=' + q(fill) + ',color=' + q(border) + ',style=' + q(style) + '];')
        lines.append('}')
    for e in edges:
        attrs = ['id=' + q(e['id']), 'label=' + q(e['label'])]
        attrs += {'data': [], 'control': ['color="#176bc0"'],
                  'sequence': ['color="#c53249"', 'penwidth=2.2'],
                  'condition': ['color="#b67c24"', 'style=dashed'],
                  'state': ['color="#308154"', 'style=dashed', 'constraint=false'],
                  'annotation': ['color="#8b7896"', 'style=dotted', 'constraint=false']}[e['kind']]
        lines.append(q(e['source']) + ' -> ' + q(e['target']) + ' [' + ','.join(attrs) + '];')
    lines.append('}')
    dot = output / 'architecture.dot'
    dot.write_text('\n'.join(lines) + '\n')
    for fmt in ('svg', 'png'):
        args = ['dot', '-T' + fmt]
        if fmt == 'png':
            args += ['-Gsize=85,60', '-Gdpi=100']
        subprocess.run(args + [str(dot), '-o', str(output / ('architecture.' + fmt))], check=True)
    svg = (output / 'architecture.svg').read_text()
    xml = ET.fromstring(svg)
    ids = {x.get('id') for x in xml.iter() if x.get('id')}
    require(all(n['id'] in ids for n in nodes.values()) and all(e['id'] in ids for e in edges), 'SVG IDs missing')
    svg = svg[svg.index('<svg'):]
    data = dict(nodes=nodes, edges=edges, source=spec['source'], profile=spec['profile'], view=view)
    template = (Path(__file__).resolve().parent.parent / 'assets/viewer-template.html').read_text()
    # Single-pass replacement avoids interpreting placeholder-like user/source text.
    replacements = {'__TITLE__': html.escape(title), '__PROVENANCE__': html.escape('源码：' + (src.revision or '工作区字节审计')),
                    '__LEGEND__': html.escape(LEGEND), '__SVG__': svg,
                    '__GRAPH_DATA__': json.dumps(data, ensure_ascii=False).replace('<', '\\u003c')}
    page = re.sub('|'.join(map(re.escape, replacements)), lambda m: replacements[m.group()], template)
    (output / 'architecture.html').write_text(page)
    (output / 'graph.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    return dict(view=view, nodes=len(nodes), edges=len(edges), html=str(output / 'architecture.html'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', required=True)
    parser.add_argument('--source-root', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--full-dir', default='full')
    parser.add_argument('--inference-dir', default='inference')
    parser.add_argument('--font', default='Noto Sans CJK SC')
    args = parser.parse_args()
    require(shutil.which('dot'), 'Graphviz dot is required')
    require(args.full_dir != args.inference_dir, 'Output directories must differ')
    for name in (args.full_dir, args.inference_dir):
        require(re.fullmatch(r'[A-Za-z0-9_-]+', name), 'Output directory must be a simple name')
    spec = copy.deepcopy(json.loads(Path(args.spec).read_text()))
    src = Source(args.source_root, spec.get('source', {}).get('revision'))
    if src.revision:
        spec['source']['revision'] = src.revision
    report = validate(spec, src)
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    results = [render(spec, src, v, output / d, args.font)
               for v, d in [('full', args.full_dir), ('inference', args.inference_dir)]]
    report['views'] = results
    (output / 'shape_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (output / 'source_audit.json').write_text(json.dumps(src.audit(), ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
