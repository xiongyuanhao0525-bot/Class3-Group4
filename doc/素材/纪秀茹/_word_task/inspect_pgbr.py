# -*- coding: utf-8 -*-
"""检查 3.4 代码质量问题 标题段落的 OOXML 分页属性。"""
import zipfile
from lxml import etree

p = r'C:\Users\16570\AppData\Local\Doubao\User Data\Default\DoubaoStorage\Aida\doubao-office\ai-edit\2B2EO7HaNFl3HHLAhd50GPpRXoW-1792824506708-9dl4vsxxlcm.docx'
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W}
z = zipfile.ZipFile(p)
root = etree.fromstring(z.read('word/document.xml'))
paras = root.findall('.//w:body/w:p', NS)
print('body paragraphs:', len(paras))
for i, para in enumerate(paras):
    txt = ''.join(t.text or '' for t in para.findall('.//w:t', NS))
    if '代码质量问题' in txt or '编程技能' in txt or '表情反应切换' in txt:
        pPr = para.find('w:pPr', NS)
        attrs = []
        if pPr is not None:
            for tag in ['w:pageBreakBefore', 'w:keepNext', 'w:keepLines']:
                e = pPr.find(tag, NS)
                attrs.append(tag.split(':')[1] + '=' + ('yes' if e is not None else 'no'))
            # numPr / style
            st = pPr.find('w:pStyle', NS)
            attrs.append('pStyle=' + (st.get('{%s}val' % W) if st is not None else 'none'))
        brs = para.findall('.//w:br', NS)
        brinfo = [(b.get('{%s}type' % W)) for b in brs]
        print(i, repr(txt[:20]), attrs, 'brs=', brinfo)
# 也检查列表项段落（w:p 含 numPr 的标题其实在 w:p 里）
print('---')
for i, para in enumerate(paras):
    pPr = para.find('w:pPr', NS)
    if pPr is None:
        continue
    numPr = pPr.find('w:numPr', NS)
    txt = ''.join(t.text or '' for t in para.findall('.//w:t', NS))
    if numPr is not None and ('代码质量问题' in txt or '编程技能' in txt):
        pb = pPr.find('w:pageBreakBefore', NS)
        kn = pPr.find('w:keepNext', NS)
        print('listitem', i, repr(txt[:20]), 'pageBreakBefore=', pb is not None, 'keepNext=', kn is not None)
