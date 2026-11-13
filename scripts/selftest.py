#!/usr/bin/env python3
"""Smoke test rendering, view isolation, provenance, and rejection of invalid graphs.

Does not import torch or execute the fixture model. Output is suitable for browser QA.
"""
import argparse
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from source_inventory import Source, inventory
from render_diagrams import validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='Use a new temporary directory')
    args = parser.parse_args()
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    model = '''import torch
from torch import nn
class TinyNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv = nn.Conv2d(3, 8, 3, stride=2, padding=1)
        self.head = nn.Linear(8, 4)
    def forward(self, x):
        feature = self.conv(x)
        pooled = feature.mean(dim=(-2, -1))
        return self.head(pooled)
def training_step(model, x, target):
    logits = model(x)
    return torch.nn.functional.cross_entropy(logits, target)
'''
    (root / 'model.py').write_text(model)
    both = ['full', 'inference']
    def port(name, shape, axes):
        return dict(name=name, shape=shape, axes=axes, dtype='float32',
                    basis='B=1，输入32×32；Conv k3/s2/p1；mean(H,W)；Linear(8,4)', status='derived')
    def node(title, inputs, outputs, line, views=both, kind='base'):
        return dict(title=title, body='源码静态推导，无权重执行。', cluster='model', kind=kind, views=views,
                    source_refs=[dict(path='model.py', line=line)], inputs=copy.deepcopy(inputs), outputs=copy.deepcopy(outputs))
    x = port('x', '[1,3,32,32]', 'B,C,H,W')
    feat = port('feature', '[1,8,16,16]', 'B,C,H,W')
    pooled = port('pooled', '[1,8]', 'B,C')
    logits = port('logits', '[1,4]', 'B,classes')
    loss = port('loss', '[]', 'scalar')
    target = dict(name='target', shape='[1]', axes='B', dtype='int64', basis='CE类别标签', status='derived')
    spec = dict(schema_version=1, title='TinyNet <源码验证>', source={}, profile='B=1；32×32；CPU float32',
                configs=[], symbols={'B': '1'}, switches=[], verification=['静态核对；未import torch或执行模型'],
                clusters={'model': '计算图'}, nodes={
                    'input': node('图像输入', [], [x], 8),
                    'conv': node('Conv2d 3→8', [x], [feat], 9),
                    'pool': node('空间均值池化', [feat], [pooled], 10),
                    'head': node('Linear 8→4', [pooled], [logits], 11, kind='out'),
                    'target': node('训练标签', [], [target], 12, ['full'], 'train'),
                    'loss': node('训练交叉熵', [logits, target], [loss], 14, ['full'], 'train')}, edges=[])
    for a, b, name, views in [('input', 'conv', 'x', both), ('conv', 'pool', 'feature', both),
                              ('pool', 'head', 'pooled', both), ('head', 'loss', 'logits', ['full']),
                              ('target', 'loss', 'target', ['full'])]:
        spec['edges'].append(dict(source=a, target=b, kind='data', views=views, meaning='传递' + name,
                                  source_port=name, target_port=name))
    spec['edges'].append(dict(source='conv', target='head', kind='sequence', views=both,
                              meaning='卷积返回后才执行head；中间先池化，无并发执行。'))
    spec_path = root / 'architecture.json'
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2))
    subprocess.run([sys.executable, str(Path(__file__).with_name('render_diagrams.py')),
                    '--spec', str(spec_path), '--source-root', str(root), '--output', str(root / 'rendered')], check=True)
    full = json.loads((root / 'rendered/full/graph.json').read_text())
    inference = json.loads((root / 'rendered/inference/graph.json').read_text())
    assert 'loss' in full['nodes'] and 'loss' not in inference['nodes']
    assert not any(e['target'] == 'loss' for e in inference['edges'])
    assert len(inference['edges']) == 4
    audit = json.loads((root / 'rendered/source_audit.json').read_text())
    assert audit['mode'] == 'working-tree'
    assert audit['files'][0]['sha256'] == hashlib.sha256(model.encode()).hexdigest()
    assert any(s['name'] == 'TinyNet.forward' for s in inventory(Source(root))['files'][0]['symbols'])
    for kind in ('shape', 'dtype', 'training_view', 'line'):
        broken = copy.deepcopy(spec)
        if kind == 'shape':
            broken['nodes']['conv']['inputs'][0]['shape'] = '[2,3,32,32]'
        elif kind == 'dtype':
            broken['nodes']['conv']['inputs'][0]['dtype'] = 'float16'
        elif kind == 'training_view':
            broken['nodes']['loss']['views'] = both
        else:
            broken['nodes']['conv']['source_refs'][0]['line'] = 9999
        try:
            validate(broken, Source(root))
        except ValueError:
            pass
        else:
            raise AssertionError('Expected rejection: ' + kind)
    unknown = copy.deepcopy(spec)
    unknown['nodes']['loss']['outputs'][0].update(shape='?', status='unknown', basis='示例：缺少输出约定')
    assert len(validate(unknown, Source(root))['unknown_ports']) == 1
    print('PASS: shape/dtype/source checks, training isolation, unknown reporting, inventory, SVG IDs and both render views')
    print('Browser QA entry:', root / 'rendered/inference/architecture.html')


if __name__ == '__main__':
    main()
