"""Summarize the completed source-bound training-core experiment."""
from pathlib import Path
import csv
import hashlib
import json
import random
import statistics

HERE=Path(__file__).resolve().parent


def quantile(v,p):
    v=sorted(v);x=(len(v)-1)*p;i=int(x)
    return v[i] if i==len(v)-1 else v[i]*(1-x+i)+v[i+1]*(x-i)


def main():
    report=json.loads((HERE/'GROWTH_CALIBRATION_REPORT.json').read_text())
    rows=[json.loads(x) for x in (HERE/'CAREER_PATHS.jsonl').read_text().splitlines()]
    contrasts=[];rng=random.Random(2006000701)
    for a,b in [('PA191_NATIONAL_USER','PA191_CLUB_USER'),('PA191_NATIONAL_USER','PA191_NATIONAL_NPC'),('PA191_NATIONAL_NPC','PA175_NATIONAL_NPC')]:
        aa=[r['samples']['30']['CA'] for r in rows if r['arm']==a]
        bb=[r['samples']['30']['CA'] for r in rows if r['arm']==b]
        draws=[statistics.mean(rng.choices(aa,k=len(aa)))-statistics.mean(rng.choices(bb,k=len(bb))) for _ in range(2000)]
        contrasts.append(dict(arm_a=a,arm_b=b,age=30,mean_difference=statistics.mean(aa)-statistics.mean(bb),
                              bootstrap_percentile95=[quantile(draws,.025),quantile(draws,.975)],resamples=2000))
    analysis=dict(status='COMPLETED',source_report_sha256=hashlib.sha256((HERE/'GROWTH_CALIBRATION_REPORT.json').read_bytes()).hexdigest(),
                  analysis_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  bootstrap_seed=2006000701,conditional_CA30_contrasts=contrasts)
    (HERE/'GROWTH_CONTRASTS.json').write_text(json.dumps(analysis,ensure_ascii=False,indent=2))
    with (HERE/'SYNTHETIC_GROWTH_SUMMARY.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['arm','age','n','mean_CA','p05_CA','median_CA','p95_CA','CA180_rate','CA185_rate','CA190_rate','CA180_Wilson95','CA185_Wilson95','CA190_Wilson95'])
        for arm,d in report['arms'].items():
            for age,v in d['ages'].items():
                w.writerow([arm,age,v['n'],v['mean'],v['quantiles']['0.05'],v['quantiles']['0.5'],v['quantiles']['0.95'],
                            *[v['attainment'][str(t)]['rate'] for t in (180,185,190)],*[json.dumps(v['attainment'][str(t)]['Wilson95']) for t in (180,185,190)]])
    lines=['# 已有V1.18长期成长审计与独立路径实验','',
           '范围：此前发布的V1.18（提交5efc9c6449617a415668896abecf37a8e0ad24ad），不是新上传但尚不可读取的2004—2006全量交接包。未读取新包的根任务书、源清单或2006完整角色卡；不据此重建2006主角XP、伤病或永久子值。原源码没有修改。','',
           '## 实际完成的实验','',
           '执行`python calibrate_training_core.py --workers 3`：1000个互不相同的种子、4组各250条独立合成训练路径，18至30岁，每条288个半月阶段，共288000次阶段结算。输入43子项/P6来自同一个数值模板，全部改为合成身份，起始CA159，XP从正式初始化银行开始。这个模板不是2006年费德勒的恢复卡。','',
           '四组只比较PA、训练环境与名义角色：PA191俱乐部；PA191国家级（user）；PA191国家级（NPC）；PA175国家级（NPC）。固定均衡成长先验，持续轮换两个技术大类和一个P6大类，不专精、不生成正式比赛、不赠送冠军、不施加人工伤病。不同路径分别初始化潜力形状、峰龄和训练随机流。','',
           '为节省复制开销，使用原始数值核心`Training/v118.py::_settle`，没有改写或绕过数值算法；另以完整288阶段逐次对比公开`Training.v1_18.settle_phase`，回执和状态完全相等。每条路径末尾调用正式`load_state(dump_state)`验证XP质量守恒与合法性。','',
           '预声明、完整输入和源码SHA见`growth/PREDECLARED_GROWTH_PLAN.json`；1000条路径的年龄采样和银行余额在`growth/CAREER_PATHS.jsonl`。统计文件在`growth/GROWTH_CALIBRATION_REPORT.json`、`growth/SYNTHETIC_GROWTH_SUMMARY.csv`。峰龄只观测至30岁，属于右删失窗口，不宣称30岁以后绝无更高峰。','',
           '| 组别（各250） | 20岁CA中位数 | 23岁 | 26岁 | 28岁 | 30岁 | 已观测峰值均值 | 峰值≥190比例 |','| --- | --- | --- | --- | --- | --- | --- | --- |']
    for arm,d in report['arms'].items():
        vals=[d['ages'][str(a)]['quantiles']['0.5'] for a in (20,23,26,28,30)]
        lines.append('| '+arm+' | '+' | '.join(str(v) for v in vals)+f" | {d['peak_CA_mean']:.3f} | {d['peak_attainment']['190']['rate']:.1%} |")
    lines+=['','每年龄CA180/185/190比例和Wilson95%区间均已输出，不用1000总样本替代各组250的置信区间。2000次固定种子的百分位bootstrap只用于本条件模板的CA30均值差：','']
    for c in contrasts:
        lines.append(f"- {c['arm_a']}减{c['arm_b']}：{c['mean_difference']:.3f} CA，bootstrap95% [{c['bootstrap_percentile95'][0]:.3f}, {c['bootstrap_percentile95'][1]:.3f}]。")
    lines+=['','上述均值差区间为条件性的探索结果，未进行多重比较校正。user/NPC两组同时使用不同合成ID和独立种子，不能把其0.176CA均值差解释成角色标签的因果奖励；同身份同种子的配对角色探针才隔离了该标签。','',
            '训练受阻的账本证据：PA191国家级两组30岁时，平均未花费技术XP分别约30605与30892，约42.9/43个专项已无完整一级的软上限空间；PA191俱乐部组平均银行约9919XP，却只有约2.2项被同一判据判为上限受阻。前者主要是结构上限/身体支持约束，后者还受训练强度、许可或子项分配影响。单纯把全部高PA训练XP乘大，会大量增加已达上限项的银行，不能保证额外永久成长。']
    lines+=['','## 核心数值链与具体发现','',
           '1. 正式经验与兑换。`Training/v1_18.py:38`按唯一来源入43项同一XP银行，`Training/v118.py:107`统一检查成本、许可与软上限，之后才增加子值；`Training/v1_18.py:138`校验累计入账减花费等于银行余额。比赛、观赛与冠军没有第二套永久技术点。不能把一场估计4.655XP直接视为已兑换G或CA。','',
           '2. 成本确实非线性。`runtime/career_v114.py:12`：子值100/120/128/138/145/149的下一级XP成本分别8.30/11.46/16.98/31.06/50.24/65.16；128/138/145起分别要1/2/3许可。这会造成高阶放缓，但许可、身体支持、专项是否获训也应同时查，不能只把XP倍率调高。','',
           '3. PA普通训练倍率温和。PA150/175/191/200分别1.0000/1.0875/1.1435/1.1750；PA191与175的倍率比仅约1.0515。`runtime/career_v118.py:92`另外根据PA±1推断未来43项/P6结构空间，不改变当前子值；`Training/v118.py:15`生成25.8—30.8范围内的身体峰龄先验。`runtime/career_v118.py:406`每年仅凭实际持续成长或证据上修PA，普通老化不自动降低终身PA。','',
           '4. 环境比PA学习倍率差异更大。`runtime/career_v116.py:24`与`Training/v118.py:130`：俱乐部训练质量1.00、国家级2.13；还分别叠加运动科学1.00/1.25与恢复1.00/1.10。这个差异在直接成长、专项XP与P6上共同起作用，足以解释常规与优质路径的差别。实验不支持“PA191在现有引擎中无论如何只能每年+2CA”的结论；实际2006是否缺训练/XP对账必须读新历史收据后再判。','',
           '5. 年龄存在硬边界，应列为未来前向补丁候选。`runtime/career_v118.py:232`在22岁从1.12跳到1.04，在25岁从1.04跳到0.96，分别突降约7.14%与7.69%；23岁后身体训练采用连续指数，27岁自然P6成熟却直接归0（同文件:264）。`growth/ROLE_AND_AGE_PROBES.json`保留边界探针。建议用局部平滑曲线保持远离边界的原倍率，再与冻结基线对照；本次未擅自修改既有年份或声称已校准。','',
           '6. P6下降与学习记忆分开。`runtime/career_v118.py:191`按当前身体收缩可发挥的软上限；`:204`输出有效children、learned_children、CA和learned_CA；`:256`按年龄逐月降低身体及可训练上限，技术记忆衰退更迟更慢。`runtime/card_training_v112.py:127`唯一聚合43项→G9→G均值和P6均值→CA，PA不直接压低此CA。恢复2006时必须保留“学会的值”和“当前身体可发挥的值”，不能把伤病导致的差额删成技术永久损失。','',
           '7. 技术XP不自动过期，但P6银行不同。`Training/v118.py:175`将P6 XP容量限制在当前一次兑换成本，溢出明确计入`P_XP_EXPIRED_AT_BANK_CAP`；因此“任何XP永久保留”的笼统说法不准确。技术到上限后仍可积累XP与许可，属于已保留但受身体/潜在上限限制的余额；应在卡上显示受阻原因。','',
           '8. 奖励是补充，不会自动产生冠军级跳跃。`Training/v1_18.py:67`比赛XP有单项20%、单场8和阶段上限；冠军显式XP总额至多3、发展奖励滚动12个月总额12。`runtime/career_v118.py:296`的训练窗口另按质量给最多25%、两个月并取重叠最大。奖励与正常训练相比规模小，不能以冠军次数直接推算CA。','',
           '9. 专精负荷的代价真实存在。`Training/v118.py:237`基础负荷14，每个专精大类再加2；俱乐部恢复14、国家级15.4，持续双专精分别每阶段净增4与2.6疲劳。`runtime/career_v118.py:242`从疲劳35起降低全部成长效率。本文矩阵不做专精且无赛事。正式初始化默认疲劳18；俱乐部组阶段后观测最高疲劳18，国家级各组16.6，随后恢复下降；全部组疲劳≥70的阶段数为0。这是没有持续高负荷暴露的条件实验，不是现实伤病率为0。','',
           '## 公平与不能推断的范围','',
           '除独立种子NPC对照外，还在同一身份、同一种子上只切换user/NPC标签，50个种子×每角色24阶段，所有状态与回执完全相等。该结果证明此训练数值管不读取角色标签来偏袒主角；不证明World默认NPC计划、资源、参赛负荷与主角相同。','',
           '这是无比赛、无伤病暴露、无退役决策的训练核心条件实验。伤病发生率与退出率明确记NOT_MODELLED，不能输出0%来冒充总体结论。1000条路径彼此独立，但都条件于同一个初始数值模板，并非1000种独立天赋的真实人口；高PA优质训练中的190比例不能推广为所有职业球员的190稀有度。它也不能认证国家队环境系数来自体育论文。','',
           '## 最小修复顺序建议','',
           '先读全量历史与源清单，确认2006年43/P6、两套XP余额、许可、训练时钟、伤病与已兑现来源；缺项保留unknown。然后提供年龄连续性与更清楚受阻诊断的可关前向补丁。继续用冻结输入、相同种子与等PA NPC对照检查效果，再决定是否有证据提高普通训练或稀有突破奖励。不要先为使主角CA达标而抬高所有高PA倍率，更不要反算改写2004—2006。','',
           '复跑时先把`calibrate_training_core.py`复制到空实验目录，再设置`SPIN_ERA_ENGINE_ROOT`为冻结引擎目录后运行；脚本拒绝覆盖既有预声明或原始结果。',
           '',f"本实验完成耗时{report['elapsed_seconds']:.1f}秒；没有修改任何引擎、没有推进用户世界或2007正式赛事。"]
    (HERE.parent/'BASELINE_GROWTH_AUDIT.md').write_text('\n'.join(lines)+'\n')
    print('growth contrast, CSV and audit report written')


if __name__=='__main__':main()
