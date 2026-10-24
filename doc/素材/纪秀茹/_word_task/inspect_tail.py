# -*- coding: utf-8 -*-
"""检查 body 级 sectPr 属性与文档末尾段落结构。"""
import zipfile
from lxml import etree

p = r'C:\Users\16570\AppData\Local\Doubao\User Data\Default\DoubaoStorage\Aida\doubao-office\ai-edit\2B2EO7HaNFl3HHLAhd50GPpRXoW-1792824856555-fh24ao33pwh.docx'
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W}
z = zipfile.ZipFile(p)
root = etree.fromstring(z.read('word/document.xml'))
body = root.find('w:body', NS)
bs = body.find('w:sectPr', NS)
print('--- body-level sectPr ---')
print(etree.tostring(bs, pretty_print=True, encoding='unicode'))
print('--- last 6 body children ---')
kids = list(body)
for k in kids[-6:]:
    tag = etree.QName(k).localname
    if tag == 'p':
        txt = ''.join(t.text or '' for t in k.findall('.//w:t', NS))
        pPr = k.find('w:pPr', NS)
        pb = pPr.find('w:pageBreakBefore', NS) if pPr is not None else None
        brs = [b.get('{%s}type' % W) for b in k.findall('.//w:br', NS)]
        print('P', repr(txt[:30]), 'pbb=', pb is not None, 'brs=', brs)
    else:
        print(tag)
