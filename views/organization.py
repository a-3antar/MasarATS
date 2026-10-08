"""صفحة الهيكل التنظيمي بنفس تصميم صفحتي الوظائف والمرشحين: مؤشرات + بحث وفلاتر + جدول مع لوحة تفاصيل + بطاقات.
ربط الهيكل بالوظائف: من فجوة القوى العاملة تُنشأ وظيفة مسودة (طلب توظيف) ويُبحث عن مرشحين بمحرك المطابقة نفسه."""

import html

import pandas as pd
import streamlit as st

from core.constants import SEARCH_MAX_CANDIDATES
from core.exceptions import SmartATSError
from database.database import get_db_session
from services.candidate_service import CandidateService
from services.job_service import JobService
from services.matching_service import MatchingService
from services.organization_service import OrganizationService
from ui import job_components as jobs_ui
from ui import org_components as ui

_CACHE_TTL = 30
_CARD_COLUMNS = 3
_TOP_CANDIDATES = 10
_SELECTED_POS_KEY = "org_selected_position"
_SEARCH_KEY = "org_candidate_search"
_NONE_DEPT = "— بدون قسم —"
_NONE_BOSS = "— لا يتبع أحداً —"
_CLOSED = "Closed"
_FULL_PCT = 100

_NAV_KEY, _JOBS_PAGE, _MATCHING_PAGE = "nav_page", "💼 الوظائف", "🎯 المطابقة"
_JOBS_SELECTED_KEY, _MATCHING_JOB_KEY = "jobs_selected_id", "m_job_select"
_JOB_STATUS_LABELS = {"Draft": "مسودة", "Open": "مفتوحة", "On Hold": "معلّقة", "Closed": "مغلقة"}


# ------------------------------------------------------------ بيانات وكاش

@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def _overview() -> dict:
    with get_db_session() as session:
        return OrganizationService(session).overview()


def _invalidate() -> None:
    """مسح كاش الهيكل وكاش الوظائف (الهيكل مرتبط بالوظائف فيتأثر الاثنان)."""
    _overview.clear()
    try:
        from views import jobs as _jobs
        _jobs._invalidate_job_related_caches()
    except Exception:  # noqa: BLE001
        pass


def _run(action, success: str) -> bool:
    """ينفّذ عملية على الخدمات داخل جلسة، ويعرض الخطأ للمستخدم. يعيد تشغيل الصفحة عند النجاح."""
    try:
        with get_db_session() as session:
            action(session)
    except SmartATSError as exc:
        st.error(str(exc))
        return False
    _invalidate()
    st.toast(success)
    st.rerun()
    return True


def _go_to_jobs(job_id: int) -> None:
    st.session_state[_NAV_KEY] = _JOBS_PAGE
    st.session_state[_JOBS_SELECTED_KEY] = job_id


def _go_to_matching(job_id: int, title: str) -> None:
    st.session_state[_NAV_KEY] = _MATCHING_PAGE
    st.session_state[_MATCHING_JOB_KEY] = f"{title} (#{job_id})"


def _clean_line(text: str) -> str:
    return text.lstrip("✓✔⚠❌\ufe0f ").strip()


def _index_of(options: dict, value) -> int:
    return next((i for i, v in enumerate(options.values()) if v == value), 0)


def _dept_options(overview: dict) -> dict[str, int | None]:
    return {_NONE_DEPT: None} | {f"{d['name']} (#{d['id']})": d["id"] for d in overview["departments"]}


def _position_options(overview: dict, exclude_id: int | None = None) -> dict[str, int | None]:
    return {_NONE_BOSS: None} | {
        f"{p['title']} (#{p['id']})": p["id"] for p in overview["positions"] if p["id"] != exclude_id
    }


# ------------------------------------------------------------ نوافذ الأقسام

@st.dialog("➕ إضافة قسم جديد")
def _create_department_dialog() -> None:
    parents = _dept_options(_overview())
    with st.form("new_department_form"):
        name = st.text_input("اسم القسم *")
        parent = st.selectbox("القسم الأب", list(parents), key="new_dept_parent")
        submitted = st.form_submit_button("حفظ", type="primary")
    if submitted:
        _run(lambda s: OrganizationService(s).create_department(name, parents[parent]), "تمت إضافة القسم ✅")


@st.dialog("✏️ تعديل القسم")
def _edit_department_dialog(dept_id: int) -> None:
    overview = _overview()
    dept = next((d for d in overview["departments"] if d["id"] == dept_id), None)
    if dept is None:
        st.warning("القسم غير موجود.")
        return
    parents = {label: value for label, value in _dept_options(overview).items() if value != dept_id}
    labels = list(parents)
    with st.form(f"edit_dept_{dept_id}"):
        name = st.text_input("الاسم", value=dept["name"])
        parent = st.selectbox("القسم الأب", labels, index=_index_of(parents, dept["parent_id"]))
        dept_positions = {_NONE_BOSS: None} | {
            f"{p['title']} (#{p['id']})": p["id"] for p in overview["positions"] if p["department_id"] == dept_id
        }
        manager_label = st.selectbox(
            "👑 مدير القسم", list(dept_positions), index=_index_of(dept_positions, dept.get("manager_position_id")),
            help="عند تحديده تُربط المسميات التي بلا رئيس به آلياً.",
        )
        saved = st.form_submit_button("💾 حفظ", type="primary")
    if saved:
        def save(s):
            service = OrganizationService(s)
            service.update_department(dept_id, name=name, parent_department_id=parents[parent])
            service.set_department_manager(dept_id, dept_positions[manager_label])
        _run(save, "تم الحفظ ✅")

    st.divider()
    confirm = st.checkbox("تأكيد حذف هذا القسم", key=f"confirm_del_dept_{dept_id}")
    if st.button("🗑️ حذف القسم", disabled=not confirm, key=f"del_dept_{dept_id}"):
        _run(lambda s: OrganizationService(s).delete_department(dept_id), "تم حذف القسم 🗑️")


# ------------------------------------------------------------ نوافذ المسميات الوظيفية

def _position_form_fields(key: str, overview: dict, pos: dict | None) -> dict:
    depts = _dept_options(overview)
    bosses = _position_options(overview, pos["id"] if pos else None)
    title = st.text_input("المسمى الوظيفي *", value=pos["title"] if pos else "", key=f"{key}_title")
    dept_label = st.selectbox(
        "القسم", list(depts), index=_index_of(depts, pos["department_id"] if pos else None), key=f"{key}_dept"
    )
    boss_label = st.selectbox(
        "يتبع (Reports To)", list(bosses), index=_index_of(bosses, pos["reports_to_id"] if pos else None),
        key=f"{key}_boss",
    )
    col_required, col_current = st.columns(2)
    required = col_required.number_input(
        "العدد المطلوب", min_value=0, step=1, value=pos["required"] if pos else 1, key=f"{key}_req"
    )
    current = col_current.number_input(
        "العدد الحالي", min_value=0, step=1, value=pos["current"] if pos else 0, key=f"{key}_cur"
    )
    return {
        "title": title,
        "department_id": depts[dept_label],
        "reports_to_position_id": bosses[boss_label],
        "required_headcount": int(required),
        "current_headcount": int(current),
    }


@st.dialog("➕ إضافة مسمى وظيفي", width="large")
def _create_position_dialog() -> None:
    overview = _overview()
    with st.form("new_position_form"):
        values = _position_form_fields("new_pos", overview, None)
        submitted = st.form_submit_button("حفظ", type="primary")
    if submitted:
        title = values.pop("title")
        _run(lambda s: OrganizationService(s).create_position(title, **values), "تمت إضافة المسمى الوظيفي ✅")


@st.dialog("✏️ تعديل المسمى الوظيفي", width="large")
def _edit_position_dialog(position_id: int) -> None:
    overview = _overview()
    pos = next((p for p in overview["positions"] if p["id"] == position_id), None)
    if pos is None:
        st.warning("المسمى الوظيفي غير موجود.")
        return
    with st.form(f"edit_pos_form_{position_id}"):
        values = _position_form_fields(f"edit_pos_{position_id}", overview, pos)
        saved = st.form_submit_button("💾 حفظ", type="primary")
    if saved:
        _run(lambda s: OrganizationService(s).update_position(position_id, **values), "تم الحفظ ✅")
    st.divider()
    confirm = st.checkbox("تأكيد حذف هذا المسمى", key=f"confirm_del_pos_{position_id}")
    if st.button("🗑️ حذف المسمى", disabled=not confirm, key=f"del_pos_{position_id}"):
        _run(lambda s: OrganizationService(s).delete_position(position_id), "تم الحذف 🗑️")


# ------------------------------------------------------------ ربط الهيكل بالوظائف والبحث عن مرشحين

def _create_job_for_position(position_id: int) -> None:
    """ينشئ وظيفة مسودة من المسمى (شواغرها = الفجوة) لتكمل متطلباتها من صفحة الوظائف."""
    try:
        with get_db_session() as session:
            JobService(session).create_from_position(position_id)
    except SmartATSError as exc:
        st.error(str(exc))
        return
    _invalidate()
    st.toast("تم إنشاء وظيفة مسودة — أكمل متطلباتها (المهارات والخبرة) من صفحة الوظائف ✅")
    st.rerun()


def _run_search(job_id: int) -> None:
    try:
        with st.spinner("جاري مطابقة المرشحين..."):
            with get_db_session() as session:
                job = JobService(session).get_by_id(job_id)
                candidates = CandidateService(session).list_all(limit=SEARCH_MAX_CANDIDATES)
                ranked = MatchingService(session).rank_candidates_for_job(job, candidates) if job and candidates else []
                results = [
                    {
                        "name": r["candidate"].full_name,
                        "position": r["candidate"].current_position or "-",
                        "score": r["score"],
                        "strengths": [_clean_line(s) for s in r["strengths"]],
                        "gaps": [_clean_line(g) for g in r["gaps"]],
                    }
                    for r in ranked[:_TOP_CANDIDATES]
                ]
    except SmartATSError as exc:
        st.error(str(exc))
        return
    st.session_state[_SEARCH_KEY] = {"job_id": job_id, "results": results}


def _render_candidate_search(pos: dict, prefix: str) -> None:
    """بحث مرشحين لسد فجوة مسمى: يعمل على وظيفة نشطة مرتبطة به (وإلا يعرض إنشاءها)."""
    active = [j for j in pos["jobs"] if j["status"] != _CLOSED]
    if not active:
        st.info("لا توجد وظيفة نشطة مرتبطة بهذا المسمى. أنشئ وظيفة من الفجوة ثم أكمل متطلباتها.")
        if st.button("➕ إنشاء وظيفة من الفجوة", key=f"{prefix}_mk_{pos['id']}", width="stretch"):
            _create_job_for_position(pos["id"])
        return

    labels = {f"{j['title']} (#{j['id']})": j for j in active}
    job = labels[st.selectbox("الوظيفة المرتبطة", list(labels), key=f"{prefix}_job_{pos['id']}")]

    if not job["has_requirements"]:
        st.warning("هذه الوظيفة بلا متطلبات (مهارات/خبرة)، فستكون نتائج المطابقة غير ذات معنى. أكمل المتطلبات أولاً.")
        st.button(
            "✏️ أكمل المتطلبات في صفحة الوظائف", key=f"{prefix}_req_{pos['id']}", width="stretch",
            on_click=_go_to_jobs, args=(job["id"],),
        )
        return

    if st.button("🔍 ابحث عن مرشحين مناسبين", key=f"{prefix}_find_{pos['id']}", type="primary", width="stretch"):
        _run_search(job["id"])

    state = st.session_state.get(_SEARCH_KEY)
    if not state or state["job_id"] != job["id"]:
        return
    if not state["results"]:
        st.info("لا يوجد مرشحون في قاعدة البيانات لمطابقتهم.")
        return

    st.caption(f"أفضل {len(state['results'])} مرشحين — الدرجات للعرض فقط ولا تُحفظ كتقديمات.")
    for r in state["results"]:
        st.markdown(ui.score_row(r["name"], r["position"], r["score"]), unsafe_allow_html=True)
        if r["strengths"]:
            st.caption("✔️ " + " · ".join(r["strengths"][:3]))
        if r["gaps"]:
            st.caption("⚠️ " + " · ".join(r["gaps"][:2]))
    st.button(
        "🎯 افتح المطابقة الكاملة لهذه الوظيفة", key=f"{prefix}_match_{pos['id']}", width="stretch",
        on_click=_go_to_matching, args=(job["id"], job["title"]),
    )


# ------------------------------------------------------------ المؤشرات والفلاتر

def _render_kpis(k: dict) -> None:
    cards = [
        ("🏢", "الأقسام", k["departments"], "في الهيكل التنظيمي", "muted"),
        ("🧑‍💼", "المسميات الوظيفية", k["positions"], "مسمى مسجّل", "muted"),
        ("⚠️", "إجمالي الفجوة", k["total_gap"], "شواغر مطلوب تعبئتها", "down" if k["total_gap"] else "up"),
        ("💼", "وظائف مرتبطة بالهيكل", k["linked_jobs"], "وظائف نشطة مرتبطة بمسمى", "up" if k["linked_jobs"] else "muted"),
        ("🚨", "تحذيرات", k["warnings"], "تجاوزات ونواقص", "down" if k["warnings"] else "up"),
    ]
    for col, (icon, label, value, sub, tone) in zip(st.columns(len(cards)), cards):
        col.markdown(jobs_ui.kpi_card(icon, label, value, sub, tone), unsafe_allow_html=True)


def _render_warnings(warnings: list[dict]) -> None:
    if not warnings:
        return
    with st.expander(f"🚨 تحذيرات الهيكل ({len(warnings)})", expanded=any(w["level"] == "error" for w in warnings)):
        for w in warnings:
            (st.error if w["level"] == "error" else st.warning)(w["text"], icon="🚨" if w["level"] == "error" else "⚠️")

def _render_filter_bar(overview: dict) -> dict:
    col_search, col_dept, col_gap = st.columns([3, 2, 1.3])
    query = col_search.text_input(
        "بحث", key="org_search_q", label_visibility="collapsed", placeholder="🔎 ابحث بالمسمى أو القسم..."
    )
    departments = col_dept.multiselect(
        "القسم", [d["name"] for d in overview["departments"]], key="org_f_dept", placeholder="القسم"
    )
    only_gap = col_gap.toggle("ذات فجوة فقط", key="org_f_gap")
    return {"query": query, "departments": departments, "only_gap": only_gap}


def _filter_positions(positions: list[dict], f: dict) -> list[dict]:
    needle = f["query"].strip().lower()
    return [
        p for p in positions
        if (not needle or needle in f"{p['title']} {p['department'] or ''}".lower())
        and (not f["departments"] or p["department"] in f["departments"])
        and (not f["only_gap"] or p["gap"] > 0)
    ]


# ------------------------------------------------------------ تبويب المسميات (جدول + لوحة تفاصيل)
def _table_key(rows: list[dict]) -> str:
    """مفتاح يتغير بتغير الصفوف المعروضة (فلتر/بحث) فيُصفَّر التحديد القديم."""
    return "org_positions_table_" + str(hash(tuple(r["id"] for r in rows)) & 0xFFFFFF)


def _sync_selection(rows: list[dict], table_key: str) -> None:
    """يقرأ الصف المحدد من الجدول قبل رسم اللوحة (حالة الـ widget متاحة من بداية الدورة)."""
    try:
        picked = st.session_state[table_key]["selection"]["rows"]
    except (KeyError, TypeError):
        return
    if picked and picked[0] < len(rows):
        st.session_state[_SELECTED_POS_KEY] = rows[picked[0]]["id"]


def _render_positions_table(rows: list[dict], table_key: str) -> None:
    data = [
        {
            "المسمى": p["title"],
            "القسم": p["department"] or "-",
            "المدير": "👑" if p["is_manager"] else "",
            "المستوى": p["depth"],
            "تحذير": "⚠️ " + " | ".join(p["warnings"]) if p["warnings"] else "",
            "يتبع": p["reports_to"] or "-",
            "المطلوب": p["required"],
            "الحالي": p["current"],
            "التغطية": round(min(p["current"] / p["required"] * _FULL_PCT, _FULL_PCT)) if p["required"] else _FULL_PCT,
            "الفجوة": p["gap"],
            "وظائف نشطة": p["active_jobs"],
        }
        for p in rows
    ]
    st.dataframe(
        pd.DataFrame(data), width="stretch", hide_index=True,
        on_select="rerun", selection_mode="single-row", key=table_key,
        column_config={
            "التغطية": st.column_config.ProgressColumn("التغطية", format="%d%%", min_value=0, max_value=_FULL_PCT),
        },
    )


def _render_positions_tab(rows: list[dict]) -> None:
    if not rows:
        st.info("لا توجد مسميات مطابقة للبحث والفلاتر الحالية.")
        return
    table_key = _table_key(rows)
    _sync_selection(rows, table_key)  # قبل تحديد اللوحة، وهذا هو الإصلاح

    by_id = {r["id"]: r for r in rows}
    selected = by_id.get(st.session_state.get(_SELECTED_POS_KEY)) or rows[0]

    main, side = st.columns([3, 1.15], gap="medium")
    with main:
        _render_positions_table(rows, table_key)
        st.caption(f"إجمالي المسميات: {len(rows)} — اضغط على أي صف لعرض تفاصيله والبحث عن مرشحين.")
    with side:
        _render_position_panel(selected)

def _render_position_panel(pos: dict) -> None:
    with st.container(border=True):
        st.markdown(
            f'<div class="jb"><div class="jb-title">{html.escape(pos["title"])}</div>{ui.gap_badge(pos["gap"])}</div>',
            unsafe_allow_html=True,
        )
        col_edit, col_job = st.columns(2)
        with col_edit:
            if st.button("✏️ تعديل", key=f"org_edit_pos_{pos['id']}", type="primary", width="stretch"):
                _edit_position_dialog(pos["id"])
        with col_job:
            if st.button("➕ وظيفة من الفجوة", key=f"org_mkjob_{pos['id']}", width="stretch"):
                _create_job_for_position(pos["id"])

        st.markdown('<div class="jb jb-section">📋 معلومات المسمى</div>', unsafe_allow_html=True)
        st.markdown(jobs_ui.info_rows([
            ("القسم", pos["department"] or "-"), ("يتبع", pos["reports_to"] or "-"),
            ("المطلوب", str(pos["required"])), ("الحالي", str(pos["current"])), ("الفجوة", str(pos["gap"])),
        ]), unsafe_allow_html=True)
        st.markdown(ui.headcount_bar(pos["current"], pos["required"]), unsafe_allow_html=True)
        for w in pos["warnings"]:
            st.warning(w)
        st.markdown('<div class="jb jb-section">💼 الوظائف المرتبطة</div>', unsafe_allow_html=True)
        if not pos["jobs"]:
            st.caption("لا توجد وظائف مرتبطة بهذا المسمى بعد.")
        for job in pos["jobs"]:
            col_info, col_open = st.columns([3, 1])
            badge = jobs_ui.status_badge(job["status"], _JOB_STATUS_LABELS.get(job["status"], job["status"]))
            col_info.markdown(f'{badge} {html.escape(job["title"])}', unsafe_allow_html=True)
            col_open.button(
                "فتح", key=f"org_open_job_{pos['id']}_{job['id']}", on_click=_go_to_jobs,
                args=(job["id"],), width="stretch",
            )

        st.markdown('<div class="jb jb-section">🔍 مرشحون مناسبون</div>', unsafe_allow_html=True)
        _render_candidate_search(pos, "pos")


# ------------------------------------------------------------ تبويب الفجوات

def _render_gap_tab(rows: list[dict]) -> None:
    gaps = sorted((p for p in rows if p["gap"] > 0), key=lambda p: p["gap"], reverse=True)
    if not gaps:
        st.success("لا توجد فجوات في القوى العاملة حالياً. كل المسميات مكتملة العدد.")
        return
    for pos in gaps:
        with st.container(border=True):
            col_info, col_bar, col_gap = st.columns([3, 3, 1])
            col_info.markdown(
                f'<div class="jb"><div class="jb-title">{html.escape(pos["title"])}</div>'
                f'<div class="jb-card-meta">{html.escape(pos["department"] or "بدون قسم")} · '
                f'💼 {pos["active_jobs"]} وظيفة نشطة</div></div>',
                unsafe_allow_html=True,
            )
            col_bar.markdown(ui.headcount_bar(pos["current"], pos["required"]), unsafe_allow_html=True)
            col_gap.metric("الفجوة", pos["gap"])
            with st.expander("🔍 مرشحون مناسبون لهذه الفجوة"):
                _render_candidate_search(pos, "gap")


# ------------------------------------------------------------ تبويبا الشجرة والأقسام
_TREE_MODES = {"🏢 حسب الأقسام": "departments", "🔗 حسب خطوط التبعية": "reporting"}


def _render_tree_tab(overview: dict) -> None:
    if not overview["departments"] and not overview["positions"]:
        st.info("أضف أقساماً ومسميات وظيفية أولاً لعرض الهيكل التنظيمي.")
        return
    label = st.radio("طريقة العرض", list(_TREE_MODES), horizontal=True, key="org_tree_mode")
    st.markdown(
        ui.tree_html(overview["departments"], overview["positions"], _TREE_MODES[label]),
        unsafe_allow_html=True,
    )
    st.caption("«↗ يتبع» تعني أن رئيس المسمى في قسم آخر. و👑 مدير القسم.")

def _render_departments_tab(overview: dict) -> None:
    departments = overview["departments"]
    if not departments:
        st.info("لا توجد أقسام بعد. اضغط «➕ قسم» للبدء.")
        return
    names = {d["id"]: d["name"] for d in departments}
    columns = st.columns(_CARD_COLUMNS)
    for index, dept in enumerate(departments):
        with columns[index % _CARD_COLUMNS], st.container(border=True):
            st.markdown(
                f'<div class="jb"><div class="jb-title">{html.escape(dept["name"])}</div>'
                f'<div class="jb-card-meta">يتبع: {html.escape(names.get(dept["parent_id"], "—"))}</div>'
                f'<div class="jb-card-nums"><span>🧑‍💼 {dept["positions"]}</span><span>💼 {dept["jobs"]}</span></div></div>',
                unsafe_allow_html=True,
            )
            if st.button("✏️ تعديل", key=f"org_edit_dept_{dept['id']}", width="stretch"):
                _edit_department_dialog(dept["id"])


# ------------------------------------------------------------ الصفحة الرئيسية

def render() -> None:
    ui.inject_css()

    col_title, col_dept, col_pos = st.columns([4, 1, 1.4])
    with col_title:
        st.header("🏢 الهيكل التنظيمي")
        st.caption("الأقسام والمسميات الوظيفية وفجوة القوى العاملة، مرتبطة بالوظائف والمطابقة")
    with col_dept:
        st.write("")
        if st.button("➕ قسم", key="org_add_dept", width="stretch"):
            _create_department_dialog()
    with col_pos:
        st.write("")
        if st.button("➕ مسمى وظيفي", key="org_add_pos", type="primary", width="stretch"):
            _create_position_dialog()

    overview = _overview()
    _render_kpis(overview["kpis"])

    if not overview["departments"] and not overview["positions"]:
        st.info("ابدأ بإضافة قسم ثم مسميات وظيفية لبناء الهيكل التنظيمي.")
        return

    rows = _filter_positions(overview["positions"], _render_filter_bar(overview))

    tab_positions, tab_gap, tab_tree, tab_depts = st.tabs(
        ["🧑‍💼 المسميات الوظيفية", "⚠️ فجوة القوى العاملة", "🌳 الشجرة التنظيمية", "🏢 الأقسام"]
    )
    with tab_positions:
        _render_positions_tab(rows)
    with tab_gap:
        _render_gap_tab(rows)
    with tab_tree:
        _render_tree_tab(overview)
    with tab_depts:
        _render_departments_tab(overview)

def _render_study_tab(overview: dict) -> None:
    study = OrganizationService.staffing_study(overview["positions"])
    if not study:
        st.success("لا يوجد احتياج حالياً: كل المسميات مكتملة.")
        return
    st.caption("مرتبة بالأولوية: المدراء ثم الأعلى في الهرم ثم الأكبر فجوة. «غير مغطّى» = الفجوة − شواغر الوظائف المفتوحة.")
    st.dataframe(
        pd.DataFrame([
            {
                "المسمى": r["title"], "القسم": r["department"] or "-", "يتبع": r["reports_to"] or "-",
                "المطلوب": r["required"], "الحالي": r["current"], "الفجوة": r["gap"],
                "شواغر مفتوحة": r["open_vacancies"], "غير مغطّى": r["uncovered"],
                "الإجراء المقترح": r["action"],
            }
            for r in study
        ]),
        hide_index=True, width="stretch",
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("إجمالي الفجوة", sum(r["gap"] for r in study))
    c2.metric("شواغر مفتوحة", sum(r["open_vacancies"] for r in study))
    c3.metric("غير مغطّى", sum(r["uncovered"] for r in study))