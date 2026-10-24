# -*- coding: utf-8 -*-
import zipfile
from lxml import etree

p = r'C:\Users\16570\Class3-Group4\doc\开源软件质量分析报告-DjangoBlog.docx'
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W}
z = zipfile.ZipFile(p)
root = etree.fromstring(z.read('word/document.xml'))
tbl = root.find('.//w:tbl', NS)
grid = tbl.find('w:tblGrid', NS)
print('gridCols:', [c.get('{%s}w' % W) for c in grid.findall('w:gridCol', NS)])
trs = tbl.findall('w:tr', NS)
print('rows:', len(trs))


def cellinfo(tr):
    out = []
    for tc in tr.findall('w:tc', NS):
        tcPr = tc.find('w:tcPr', NS)
        w = tcPr.find('w:tcW', NS) if tcPr is not None else None
        td = tcPr.find('w:textDirection', NS) if tcPr is not None else None
        out.append((w.get('{%s}w' % W) if w is not None else None,
                    w.get('{%s}type' % W) if w is not None else None,
                    td is not None))
    return out


print('row0(header):', cellinfo(trs[0]))
for tr in trs:
    txt = ''.join(tr.itertext())
    if '陈汉佳' in txt:
        print('chj row:', cellinfo(tr))
    if '熊圆好' in txt:
        print('xyh row:', cellinfo(tr))
