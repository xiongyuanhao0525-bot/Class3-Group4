# -*- coding: utf-8 -*-
"""列出文档所有分节符位置（段内 sectPr + body 级 sectPr）。"""
import zipfile
from lxml import etree

p = r'C:\Users\16570\AppData\Local\Doubao\User Data\Default\DoubaoStorage\Aida\doubao-office\ai-edit\2B2EO7HaNFl3HHLAhd50GPpRXoW-1792824506708-9dl4vsxxlcm.docx'
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W}
z = zipfile.ZipFile(p)
root = etree.fromstring(z.read('word/document.xml'))
body = root.find('w:body', NS)
paras = body.findall('w:p', NS)
print('paras:', len(paras))
for i, para in enumerate(paras):
    pPr = para.find('w:pPr', NS)
    if pPr is not None and pPr.find('w:sectPr', NS) is not None:
        txt = ''.join(t.text or '' for t in para.findall('.//w:t', NS))
        sect = pPr.find('w:sectPr', NS)
        typ = sect.find('w:type', NS)
        print('para', i, 'has sectPr type=', typ.get('{%s}val' % W) if typ is not None else None,
              '| text=', repr(txt[:24]))
bs = body.find('w:sectPr', NS)
print('body-level sectPr:', bs is not None)
if bs is not None:
    typ = bs.find('w:type', NS)
    print('  type=', typ.get('{%s}val' % W) if typ is not None else 'nextPage/default')
