"""Fixed texts of the demo: scenarios, the campus hint, and the English-gloss prompt."""

SCENARIOS = [
    # S1-S4 are the scenarios of the paper (Section 4.2); S5 shows the cost comparison on a type-level question
    dict(id="S1", q="今天田径场几点开放？", d="2026-01-20", zh="沉默的校区", en="silent campus",
         dzh="通知没写校区，两个校区的安排却不同", den="the notice names no campus, but the campuses differ"),
    dict(id="S2", q="通州校区寒假健身房开吗？", d="2026-02-12", zh="条件已说明", en="campus stated",
         dzh="用户说了校区，只看这一个分支", den="the visitor names the campus: one branch"),
    dict(id="S3", q="东区浴室早上几点开门？", d="2026-03-09", zh="字段被修订", en="revised field",
         dzh="新通知暂停了早场，旧安排要划掉", den="a later notice suspends the morning slot"),
    dict(id="S4", q="今年寒假浴室几点开放？", d="2025-12-28", zh="还没有通知", en="no notice yet",
         dzh="今年的寒假通知还没发，只能给往年参考", den="this year's notice is not out: last year's, labeled"),
    dict(id="S5", q="今天体育馆几点开放？", d="2026-01-20", zh="类型级问题", en="type-level question",
         dzh="问的是一类场馆，分支很多：看代价决策怎么选", den="a whole type of venue, many branches: watch the costs decide"),
]

# the campus chosen in the top bar is prepended as a user turn (the system only trusts the dialogue)
CAMPUS_HINT = {"zgc": "（我在中关村校区）", "tz": "（我在通州校区）"}

GLOSS = ("Translate this reply of a Chinese campus service assistant into plain English for a visitor. Keep every clock "
         "time and number exactly and write dates in English (1月12日 -> Jan 12); give place names in pinyin with an "
         "English gloss (e.g. Tongzhou campus); add nothing. Output JSON only: {\"en\": \"...\"}")
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
