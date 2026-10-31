# Dimension 5: table structure
source: C:\Users\16570\Desktop\文档模板-开源软件的质量分析报告文档.docx
location_base: /word/document.xml/w:body/
syntax: [T<n>] starts a table, [R<n>] a row, and [C<n>] a cell; listed defaults apply when omitted; null means unset/inherited.
table_defaults: cell_margin=w:tblCellMar(w:top(w:w="15",w:type="dxa"),w:left(w:w="15",w:type="dxa"),w:bottom(w:w="15",w:type="dxa"),w:right(w:w="15",w:type="dxa")), grid=[{"w":"993"},{"w":"843"},{"w":"5252"},{"w":"1774"}], nesting_level=0, part="word/document.xml", section_index=2, shading={"val":"clear","color":"auto","fill":"FFFFFF"}, width={"w":"0","type":"auto"}
row_defaults: header=true, height={"val":"1155"}
cell_defaults: borders=w:tcBorders(w:top(w:val="single",w:sz="4",w:space="0",w:color="auto"),w:bottom(w:val="single",w:sz="4",w:space="0",w:color="auto")), cell_margin=w:tcMar(w:top(w:w="120",w:type="dxa"),w:left(w:w="192",w:type="dxa"),w:bottom(w:w="120",w:type="dxa"),w:right(w:w="192",w:type="dxa")), paragraphs=1, shading={"val":"clear","color":"auto","fill":"FFFFFF"}, valign="center"
definitions: none
text_policy: full text is emitted without truncation.
omitted: record_type=table; repeated defaults; table text because it is the ordered concatenation of cell text; raw table XML.
normalized: loc is relative to location_base; @v references definitions; border and margin XML are losslessly compacted by tag and attributes.

[T1 loc=41]

[R1]
[C1 width={"w":"993","type":"dxa"} cell_margin=w:tcMar(w:top(w:w="120",w:type="dxa"),w:left(w:w="0",w:type="dxa"),w:bottom(w:w="120",w:type="dxa"),w:right(w:w="192",w:type="dxa"))]
成员
[C2 width={"w":"843","type":"dxa"}]
分析模块
[C3 width={"w":"5252","type":"dxa"}]
主要工作（包括注释的代码文件、每个文件注释的行数）
[C4 width={"w":"1774","type":"dxa"}]
代码注释标识（一般应为#号加个人姓名首字母）
