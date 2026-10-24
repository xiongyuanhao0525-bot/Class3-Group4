# Dimension 2: paragraph layout
source: C:\Users\16570\Desktop\文档模板-开源软件的质量分析报告文档.docx
location_base: /word/document.xml/w:body/
syntax: [P<n> ...] starts a paragraph; listed defaults apply when omitted; other missing attributes are unset/inherited; null overrides a default with unset/inherited.
defaults: part="word/document.xml", style="a3"
definitions: @v1 tabs=[{"val":"left","pos":"542"}]; @v2 numbering={"num_id":"1","level":"0"}; @v3 indent={"left":"120","right":"237","firstLine":"420"}; @v4 tabs=[{"val":"left","pos":"602"}]; @v5 numbering={"num_id":"1","level":"1"}; @v6 spacing={"before":"81","line":"242","lineRule":"auto"}; @v7 spacing={"before":"82","line":"242","lineRule":"auto"}; @v8 indent={"left":"120","right":"240","firstLine":"420"}; @v9 spacing={"before":"132","line":"242","lineRule":"auto"}; @v10 indent={"left":"120","right":"240","firstLineChars":"200","firstLine":"476"}; @v11 spacing={"before":"120","after":"120"}; @v12 indent={"left":"120","right":"240","firstLineChars":"200","firstLine":"480"}
text_policy: full text is emitted without truncation.
omitted: record_type=paragraph; repeated default values; xpath because it equals location; raw XML.
normalized: loc is body[/row/cell/block] indexes relative to location_base; @v references definitions; line_spacing duplicates spacing.line; border XML is losslessly compacted by tag and attributes.

[P1 section=1 loc=1 style="a5" special=[{"tag":"w:bookmarkStart","attrs":{"w:id":"0","w:name":"开源软件质量分析报告"},"location":"/w:document/w:body/w:p[1]/w:bookmarkStart"},{"tag":"w:bookmarkEnd","attrs":{"w:id":"0"},"location":"/w:document/w:body/w:p[1]/w:bookmarkEnd"}]]
“***”开源软件质量分析报告

[P2 section=1 loc=2 align="center" style=null]
组号：xx

[P3 section=1 loc=3 align="center" indent={"left":"2677","right":"2798"} spacing={"before":"99"}]
小组成员：xx、xx、。。。

[P4 section=1 loc=4]
<empty/>

[P5 section=1 loc=5]
<empty/>

[P6 section=1 loc=6 style="1" indent={"hanging":"422"} tabs=@v1 numbering=@v2 special=[{"tag":"w:bookmarkStart","attrs":{"w:id":"1","w:name":"1.待分析开源软件概述"},"location":"/w:document/w:body/w:p[6]/w:bookmarkStart"},{"tag":"w:bookmarkEnd","attrs":{"w:id":"1"},"location":"/w:document/w:body/w:p[6]/w:bookmarkEnd"}]]
待分析开源软件概述

[P7 section=1 loc=7 indent=@v3 spacing={"before":"133","line":"242","lineRule":"auto"}]
//<介绍待分析程序代码的名称、主要功能、编程语言及代码的整体情况（如代码行数、程序包和类的数量等）>。

[P8 section=1 loc=8]
<empty/>

[P9 section=1 loc=9]
<empty/>

[P10 section=1 loc=10 style="1" indent={"hanging":"422"} tabs=@v1 numbering=@v2 special=[{"tag":"w:bookmarkStart","attrs":{"w:id":"2","w:name":"2.软件质量分析方法及工具"},"location":"/w:document/w:body/w:p[10]/w:bookmarkStart"},{"tag":"w:bookmarkEnd","attrs":{"w:id":"2"},"location":"/w:document/w:body/w:p[10]/w:bookmarkEnd"}]]
软件质量分析方法及工具

[P11 section=1 loc=11 style="a6" indent={"hanging":"482"} spacing={"before":"215"} tabs=@v4 numbering=@v5 special=[{"tag":"w:bookmarkStart","attrs":{"w:id":"3","w:name":"2.1_分析的软件质量要素"},"location":"/w:document/w:body/w:p[11]/w:bookmarkStart"},{"tag":"w:bookmarkEnd","attrs":{"w:id":"3"},"location":"/w:document/w:body/w:p[11]/w:bookmarkEnd"}]]
分析的软件质量要素

[P12 section=1 loc=12 indent=@v3 spacing=@v6]
//<说明分析代码的哪些质量要素，如内部质量（主要关注其编码风格、设计质量等）、外部质量（如代码的缺陷、错误等）>。

[P13 section=1 loc=13 spacing={"before":"1"}]
<empty/>

[P14 section=1 loc=14 style="a6" align="both" indent={"hanging":"482"} spacing={"before":"1"} tabs=@v4 numbering=@v5 special=[{"tag":"w:bookmarkStart","attrs":{"w:id":"4","w:name":"2.2_软件质量分析方法"},"location":"/w:document/w:body/w:p[14]/w:bookmarkStart"},{"tag":"w:bookmarkEnd","attrs":{"w:id":"4"},"location":"/w:document/w:body/w:p[14]/w:bookmarkEnd"}]]
软件质量分析方法

[P15 section=1 loc=15 align="both" indent=@v3 spacing=@v6]
//<说明采用什么方法来分析代码的质量，如针对内部质量可以采用人工阅读代码、代码静态分析工具等；对于外部质量可以采用人工阅读代码、对代码进行测试等方法>

[P16 section=1 loc=16 spacing={"before":"10"}]
<empty/>

[P17 section=1 loc=17 style="a6" align="both" indent={"left":"542","hanging":"422"} tabs=@v1 numbering=@v5 special=[{"tag":"w:bookmarkStart","attrs":{"w:id":"5","w:name":"2.3软件质量分析工具"},"location":"/w:document/w:body/w:p[17]/w:bookmarkStart"},{"tag":"w:bookmarkEnd","attrs":{"w:id":"5"},"location":"/w:document/w:body/w:p[17]/w:bookmarkEnd"}]]
软件质量分析工具

[P18 section=1 loc=18 align="both" indent={"left":"120","right":"241","firstLine":"420"} spacing=@v7]
//<介绍代码质量分析工具，包括其名称、功能、支持分析哪些方面的代码质量等。>。

[P19 section=1 loc=19 spacing={"before":"4"}]
<empty/>

[P20 section=1 loc=20 style="1" indent={"hanging":"422"} tabs=@v1 numbering=@v2 special=[{"tag":"w:bookmarkStart","attrs":{"w:id":"6","w:name":"3.人工分析代码的质量情况"},"location":"/w:document/w:body/w:p[20]/w:bookmarkStart"},{"tag":"w:bookmarkEnd","attrs":{"w:id":"6"},"location":"/w:document/w:body/w:p[20]/w:bookmarkEnd"}]]
人工分析代码的质量情况

[P21 section=1 loc=21 indent={"left":"540"} spacing={"before":"132"}]
//<介绍通过人工阅读代码，所发现的代码质量情况。>

[P22 section=1 loc=22 spacing={"before":"4"}]
<empty/>

[P23 section=1 loc=23 style="a6" indent={"hanging":"482"} tabs=@v4 numbering=@v5 special=[{"tag":"w:bookmarkStart","attrs":{"w:id":"7","w:name":"3.1_代码风格"},"location":"/w:document/w:body/w:p[23]/w:bookmarkStart"},{"tag":"w:bookmarkEnd","attrs":{"w:id":"7"},"location":"/w:document/w:body/w:p[23]/w:bookmarkEnd"}]]
代码风格

[P24 section=1 loc=24 indent=@v3 spacing=@v7]
//<介绍相关程序设计语言的编码风格；结合具体的代码片段，介绍代码在多大程度上遵循了编码风格；给出相关的结论，说明该代码遵循风格的情况>

[P25 section=1 loc=25]
<empty/>

[P26 section=1 loc=26 spacing={"before":"10"}]
<empty/>

[P27 section=1 loc=27 style="a6" align="both" indent={"hanging":"482"} tabs=@v4 numbering=@v5 special=[{"tag":"w:bookmarkStart","attrs":{"w:id":"8","w:name":"3.2_代码设计"},"location":"/w:document/w:body/w:p[27]/w:bookmarkStart"},{"tag":"w:bookmarkEnd","attrs":{"w:id":"8"},"location":"/w:document/w:body/w:p[27]/w:bookmarkEnd"}]]
代码设计

[P28 section=1 loc=28 align="both" indent={"left":"120","right":"117","firstLine":"420"} spacing=@v6]
//<介绍程序设计的基本原则，如模块化、信息隐藏、高内聚度、低耦合度；结合具体代码片段（如包、类、方法等），介绍代码在多大程度上遵循设计原则；给出相关的结论，说明代码设计原则的遵循情况>

[P29 section=1 loc=29 spacing={"before":"1"}]
<empty/>

[P30 section=1 loc=30 style="a6" indent={"hanging":"482"} spacing={"before":"1"} tabs=@v4 numbering=@v5 special=[{"tag":"w:bookmarkStart","attrs":{"w:id":"9","w:name":"3.3_编程技能"},"location":"/w:document/w:body/w:p[30]/w:bookmarkStart"},{"tag":"w:bookmarkEnd","attrs":{"w:id":"9"},"location":"/w:document/w:body/w:p[30]/w:bookmarkEnd"}]]
编程技能

[P31 section=1 loc=31 indent=@v3 spacing=@v6]
//<总结该代码所体现的高水平的编程方法和技能，并结合具体代码进行示例说明。>

[P32 section=1 loc=32 spacing={"line":"242","lineRule":"auto"} style=null]
<empty/>

[P33 section=2 loc=33 style="a6" indent={"hanging":"482"} spacing={"before":"42"} tabs=@v4 numbering=@v5 special=[{"tag":"w:bookmarkStart","attrs":{"w:id":"10","w:name":"3.4_代码质量问题"},"location":"/w:document/w:body/w:p[33]/w:bookmarkStart"},{"tag":"w:bookmarkEnd","attrs":{"w:id":"10"},"location":"/w:document/w:body/w:p[33]/w:bookmarkEnd"}]]
代码质量问题

[P34 section=2 loc=34 indent={"left":"540"} spacing={"before":"81"}]
//<逐一列举：通过人工代码阅读所发现的代码中存在的质量问题和瑕疵，是否完成修复。>

[P35 section=2 loc=35 spacing={"before":"9"}]
<empty/>

[P36 section=2 loc=36 style="1" indent={"hanging":"422"} spacing={"before":"1"} tabs=@v1 numbering=@v2 special=[{"tag":"w:bookmarkStart","attrs":{"w:id":"11","w:name":"4.工具分析代码的质量情况"},"location":"/w:document/w:body/w:p[36]/w:bookmarkStart"},{"tag":"w:bookmarkEnd","attrs":{"w:id":"11"},"location":"/w:document/w:body/w:p[36]/w:bookmarkEnd"}]]
工具分析代码的质量情况

[P37 section=2 loc=37 indent=@v8 spacing=@v9]
//<概述通过工具分析所产生的代码质量整体情况，以及质量问题的修复情况。（如果数量多，也可代表性的选择）逐一指明具体的质量问题。如结合工具的代码分析情况>

[P38 section=2 loc=38 indent=@v8 spacing=@v9]
<empty/>

[P39 section=2 loc=39 style="1" indent={"hanging":"422"} spacing={"before":"1"} tabs=@v1 numbering=@v2]
小组分工

[P40 section=2 loc=40 indent=@v10 spacing=@v9]
//<列表说明每个成员分析和修复的模块>

[P41 section=2 table=1 row=1 cell=1 loc=41/1/1/2 spacing=@v11 style=null]
成员

[P42 section=2 table=1 row=1 cell=2 loc=41/1/2/2 spacing=@v11 style=null]
分析模块

[P43 section=2 table=1 row=1 cell=3 loc=41/1/3/2 spacing=@v11 style=null]
主要工作（包括注释的代码文件、每个文件注释的行数）

[P44 section=2 table=1 row=1 cell=4 loc=41/1/4/2 spacing=@v11 style=null]
代码注释标识（一般应为#号加个人姓名首字母）

[P45 section=2 loc=42 indent=@v12 spacing=@v9]
<empty/>

[P46 section=2 loc=43 indent=@v12 spacing=@v9]
<empty/>

[P47 section=2 loc=44 style="1" indent={"hanging":"422"} spacing={"before":"1"} tabs=@v1 numbering=@v2]
下一步的改进计划

[P48 section=2 loc=45 indent=@v10 spacing=@v9]
//<概述下一步将针对系统的哪些功能或不足进行改进，改进的功能点越多得分越高。>

[P49 section=2 loc=46 style="1" indent={"firstLine":"0"} spacing={"before":"1"} tabs=@v1]
<empty/>
