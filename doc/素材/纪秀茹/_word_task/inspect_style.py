# -*- coding: utf-8 -*-
"""检查 styles.xml 中 a6 样式定义及 3.3/3.4 标题段落完整上下文。"""
import zipfile
from lxml import etree

p = r'C:\Users\16570\AppData\Local\Doubao\User Data\Default\DoubaoStorage\Aida\doubao-office\ai-edit\2B2EO7HaNFl3HHLAhd50GPpRXoW-1792824506708-9dl4vsxxlcm.docx'
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W}
z = zipfile.ZipFile(p)
styles = etree.fromstring(z.read('word/styles.xml'))
for st in styles.findall('w:style', NS):
    sid = st.get('{%s}styleId' % W)
    if sid in ('a6', 'a3'):
        name = st.find('w:name', NS)
        pb = st.find('w:pPr/w:pageBreakBefore', NS)
        kn = st.find('w:pPr/w:keepNext', NS)
        based = st.find('w:basedOn', NS)
        print(sid, 'name=', name.get('{%s}val' % W) if name is not None else None,
              'basedOn=', based.get('{%s}val' % W) if based is not None else None,
              'pageBreakBefore=', pb is not None, 'keepNext=', kn is not None)
# 打印 61 段完整 XML 及相邻段
root = etree.fromstring(z.read('word/document.xml'))
paras = root.findall('.//w:body/w:p', NS)
for i in (60, 61, 62):
    print('--- para', i)
    print(etree.tostring(paras[i], pretty_print=True, encoding='unicode')[:1200])
