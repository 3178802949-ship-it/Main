# V1.1.7 综合版｜研究来源、设计依据与未完成核验

本轮没有完成“至少阅读并核实5篇原始乒乓球论文”的目标。期刊、PubMed/PMC、EuropePMC、Crossref、OpenAlex和官方人物采访原站均在代理连接阶段返回403；这不是已阅读后发现全文付费。普通和根代理的升级只读请求都没有解决该访问限制。已保留检索记录，不能把访问失败、题录线索或作者代码说明写成已读论文全文。随后通过作者公开GitHub官网源码，实际读取了3篇作者发布的论文摘要；不曾改代理或规避访问控制。

本轮实际读取了3份作者公开GitHub项目README，以及对应3篇作者项目页明确标为Abstract的论文摘要和方法说明。它们研究视频轨迹/旋转重建与机器人预判，可用于核对作者自述的方法、题目和信息边界；本轮体育学训练、负荷/年龄或专项发展原文仍未读取，没有提供本游戏PA、成长概率、性格、年龄峰值或风格倍率的实证校准。

## 实际读取的来源

| 来源 | 实际读取范围 | 可用于本轮的有限设计启发 | 不能据此声称 |
| --- | --- | --- | --- |
| Kienzle、Schön、Lienhart、Satoh：*Towards Ball Spin and Trajectory Analysis in Table Tennis Broadcast Videos via Physically Grounded Synthetic-to-Real Transfer*，作者仓库标为CVPRW/CVSports 2025 | [作者README](https://github.com/KieDani/SpinAndTrajectoryTableTennis)，固定提交`4959ad2`；[作者发布摘要](https://raw.githubusercontent.com/KieDani/kiedani.github.io/0873622ba81b639abb208779368d217f695faf65/CVPRW2025/index.html)，固定提交`0873622` | 旋转与轨迹是物理状态；视频线索、模型推断与物理真值需要分层 | 已读取原论文全文；本游戏旋转强度、到位概率或训练参数因此得到验证 |
| Kienzle、Ludwig、Lorenz、Satoh、Lienhart：*Uplifting Table Tennis: A Robust, Real-World Application for 3D Trajectory and Spin Estimation*，作者仓库标为WACV 2026 | [作者README](https://github.com/KieDani/UpliftingTableTennis)，固定提交`1a64bf6`；[作者发布摘要与方法说明](https://raw.githubusercontent.com/KieDani/kiedani.github.io/0873622ba81b639abb208779368d217f695faf65/WACV2026/index.html)，固定提交`0873622` | 球检测、摄像机校准、三维提升和旋转估计具有不同信息来源；记录应保留推断范围 | 聚合日志等于逐板观测；人物风格或生涯模型已经真实比赛校准 |
| Etaat、Kalaria、Rahmanian、Sastry：*LATTE-MV: Learning to Anticipate Table Tennis Hits from Monocular Videos*，作者仓库标为CVPR 2025 | [作者README](https://github.com/sastry-group/LATTE-MV)，固定提交`bcada1f`；[作者发布摘要](https://raw.githubusercontent.com/sastry-group/LATTE-MV/500ba2bf74433722ab5442f041e3757be4daba6c/index.html)，固定提交`500ba2b`（`gh_pages`分支） | 预判具有不确定性，不能读取对手未来隐藏决定 | README中的机器人模拟结果可直接转成人类预判成长率或比赛加成 |

上述会议、题录信息按作者仓库标注记录，未独立访问会议论文集进行复核。机器清单`data/research_v118.json`保留各自的读取范围、原论文链接、固定README及摘要地址与SHA256；`reports/v118/research/AUTHOR_REPOSITORY_READS.json`和`AUTHOR_PROJECT_ABSTRACT_READS.json`保存对应读取凭证。原论文全文读取数为0，作者发布论文摘要读取数为3；期刊/会议出版方尚未独立核验。没有将作者网页、摘要和全文混为同一种证据。

## 可继续核验的体育学文献线索

下列是待核验题录，**不是本轮已读研究，也不是本轮测试通过的证据**。作者、年份等候选信息也仍需原站核对；未填入未经核实的DOI、样本量、效果量或具体结论。

1. *Table tennis match analysis: a review*，Fuchs等，候选年份2018。[题名检索](https://pubmed.ncbi.nlm.nih.gov/?term=Table+tennis+match+analysis%3A+a+review)。后续用于核对比赛记录与技战术评价方法。
2. *Match analyses of table tennis in China: a systematic review*，Zhang、Zhou、Yang，候选年份2018。[题名检索](https://pubmed.ncbi.nlm.nih.gov/?term=Match+analyses+of+table+tennis+in+China%3A+a+systematic+review)。后续用于核对技战术分段，而非把一种分段当作唯一打法分类。
3. *A notational analysis of shot characteristics in top-level table tennis players*，Malagoli Lanzoni、Di Michele、Merni，候选年份2014。[题名检索](https://pubmed.ncbi.nlm.nih.gov/?term=A+notational+analysis+of+shot+characteristics+in+top-level+table+tennis+players)。后续用于核对击球和情境的观测指标。
4. *Physiological responses and characteristics of table tennis matches determined in official tournaments*，Zagatto、Morel、Gobatto，候选年份2010。[题名检索](https://pubmed.ncbi.nlm.nih.gov/?term=Physiological+responses+and+characteristics+of+table+tennis+matches+determined+in+official+tournaments)。后续用于核对负荷与恢复，不能由短期生理指标直接推出多年CA曲线。
5. *Perceptuo-motor skills assessment has potential as a talent detection tool in table tennis*，Faber、Oosterveld、Nijhuis-van der Sanden，候选年份2014。[题名检索](https://pubmed.ncbi.nlm.nih.gov/?term=Perceptuo-motor+skills+assessment+has+potential+as+a+talent+detection+tool+in+table+tennis)。后续用于核对专项潜能识别的不确定性。
6. *Assessing personal talent determinants in young racquet sport players: a systematic review*，Faber等，候选年份2016。[题名检索](https://pubmed.ncbi.nlm.nih.gov/?term=Assessing+personal+talent+determinants+in+young+racquet+sport+players%3A+a+systematic+review)。后续用于核对多维发展因素，不是PA数值换算公式。
7. *Head, eye and arm coordination in table tennis*，Rodrigues、Vickers、Williams，候选年份2002。[题名检索](https://pubmed.ncbi.nlm.nih.gov/?term=Head%2C+eye+and+arm+coordination+in+table+tennis)。后续用于核对知觉与执行协调，不代表读取他人想法。

第三方新闻/研究编目可以提供检索线索，却不能代替原文核验。本轮检索中发现一份公开研究bank含未核对DOI及修正记录，未将其数值、统计或声称的“已验证”状态转成本项目证据。

## 风格、性格与生涯规则如何使用这些材料

偏好轴用于描述球员化身更喜欢怎样组织比赛，例如争先阶段、主导翼、台距、节奏、旋转和风险。多个偏好可以重叠，也可以随发展调整。它们和技术能力、当下身体支持、当场情境与实际执行结果是不同层次。维度选取、轴值、倾向影响范围和标签阈值属于本游戏设计假设，不是成熟学术打法分类，也尚未通过上述文献数值校准。三篇已读摘要均不是人类多年生涯干预研究，不能据此声称“文献证明冠军奖励/国家队环境的成长系数”或“论文证明平均峰龄”。

本轮没有核实任何世界冠军的原始采访，也没有访问私人文书。`public_cues`保持空，不能写成“采访证明其真实内向/强硬/焦虑”等结论。每名球员化身可具有温和的模拟性格关键词，作为文学叙述参考；必须显式标为虚构设定，不能以姓名和冠军数推断真实私下性格。以后补充公开采访时，应记录来源、日期、原话范围和解释限制，且不得将未来采访倒灌到早年世界。

PA正常轻度上升、通常不下降、重大持续功能损失才可能损伤潜能，是本轮用户要求与游戏规则选择，不是已从论文推导出的自然定律。应与当前年龄的身体支持上限分开展示，并以实际代码测试验证守恒、范围、触发条件和长期表现。测试能验证规则实现，不会自动证明体育科学真实性。

研究核验未完成不妨碍记录可运行候选和失败结果，但不能将本轮称为“已按更多原始论文完成科学校准”。后续取得原文后，应先核对方法、样本、年龄、水平和统计限制，再决定是否需要参数改动。
