"""صفحة الهيكل التنظيمي: أقسام، مسميات وظيفية، شجرة العرض، وفجوة القوى العاملة."""

import streamlit as st

from core.exceptions import SmartATSError
from database.database import get_db_session
from services.candidate_service import CandidateService
from services.organization_service import OrganizationService

_LIST_CACHE_TTL = 30


@st.cache_data(ttl=_LIST_CACHE_TTL, show_spinner=False)
def _cached_departments() -> list:
    with get_db_session() as session:
        return OrganizationService(session).list_departments()


@st.cache_data(ttl=_LIST_CACHE_TTL, show_spinner=False)
def _cached_positions() -> list:
    with get_db_session() as session:
        return OrganizationService(session).list_positions()


def _invalidate_caches() -> None:
    _cached_departments.clear()
    _cached_positions.clear()


# ------------------------------------------------------------ الأقسام

def _render_departments_tab() -> None:
    departments = _cached_departments()
    dept_labels = {"— بدون قسم أب —": None} | {f"{d.name} (#{d.id})": d.id for d in departments}

    with st.expander("➕ إضافة قسم جديد"):
        with st.form("new_department_form", clear_on_submit=True):
            name = st.text_input("اسم القسم *")
            parent_label = st.selectbox("القسم الأب", list(dept_labels.keys()), key="new_dept_parent")
            submitted = st.form_submit_button("حفظ", type="primary")
        if submitted:
            try:
                with get_db_session() as session:
                    OrganizationService(session).create_department(name, dept_labels[parent_label])
                _invalidate_caches()
                st.toast("تمت إضافة القسم ✅")
                st.rerun()
            except SmartATSError as exc:
                st.error(str(exc))

    if not departments:
        st.info("لا توجد أقسام بعد.")
        return

    for dept in departments:
        with st.expander(f"🏢 {dept.name} (#{dept.id})"):
            with st.form(f"edit_dept_{dept.id}"):
                new_name = st.text_input("الاسم", value=dept.name, key=f"dept_name_{dept.id}")
                options = [l for l, i in dept_labels.items() if i != dept.id]
                current_label = next((l for l, i in dept_labels.items() if i == dept.parent_department_id), options[0])
                new_parent_label = st.selectbox(
                    "القسم الأب", options, index=options.index(current_label), key=f"dept_parent_{dept.id}"
                )
                saved = st.form_submit_button("💾 حفظ", type="primary")
            if saved:
                try:
                    with get_db_session() as session:
                        OrganizationService(session).update_department(
                            dept.id, name=new_name, parent_department_id=dept_labels[new_parent_label]
                        )
                    _invalidate_caches()
                    st.toast("تم الحفظ ✅")
                    st.rerun()
                except SmartATSError as exc:
                    st.error(str(exc))

            st.divider()
            confirm = st.checkbox("تأكيد حذف هذا القسم", key=f"confirm_del_dept_{dept.id}")
            if st.button("🗑️ حذف القسم", disabled=not confirm, key=f"del_dept_{dept.id}"):
                try:
                    with get_db_session() as session:
                        OrganizationService(session).delete_department(dept.id)
                    _invalidate_caches()
                    st.toast("تم حذف القسم 🗑️")
                    st.rerun()
                except SmartATSError as exc:
                    st.error(str(exc))


# -------------------------------------------------------- المسميات الوظيفية

def _render_positions_tab() -> None:
    departments = _cached_departments()
    positions = _cached_positions()
    dept_labels = {"— بدون قسم —": None} | {f"{d.name} (#{d.id})": d.id for d in departments}
    pos_labels_base = {p.id: f"{p.title} (#{p.id})" for p in positions}

    with st.expander("➕ إضافة مسمى وظيفي جديد"):
        with st.form("new_position_form", clear_on_submit=True):
            title = st.text_input("المسمى الوظيفي *")
            dept_label = st.selectbox("القسم", list(dept_labels.keys()), key="new_pos_dept")
            reports_options = {"— لا يتبع أحداً —": None} | {v: k for k, v in pos_labels_base.items()}
            reports_label = st.selectbox("يتبع (Reports To)", list(reports_options.keys()), key="new_pos_reports")
            col1, col2 = st.columns(2)
            with col1:
                required = st.number_input("العدد المطلوب", min_value=0, step=1, value=1, key="new_pos_required")
            with col2:
                current = st.number_input("العدد الحالي", min_value=0, step=1, value=0, key="new_pos_current")
            submitted = st.form_submit_button("حفظ", type="primary")
        if submitted:
            try:
                with get_db_session() as session:
                    OrganizationService(session).create_position(
                        title,
                        department_id=dept_labels[dept_label],
                        reports_to_position_id=reports_options[reports_label],
                        required_headcount=int(required),
                        current_headcount=int(current),
                    )
                _invalidate_caches()
                st.toast("تمت إضافة المسمى الوظيفي ✅")
                st.rerun()
            except SmartATSError as exc:
                st.error(str(exc))

    if not positions:
        st.info("لا توجد مسميات وظيفية بعد.")
        return

    for pos in positions:
        gap_badge = f" · فجوة: {pos.gap}" if pos.gap > 0 else ""
        with st.expander(f"🧑‍💼 {pos.title} (#{pos.id}){gap_badge}"):
            with st.form(f"edit_pos_{pos.id}"):
                new_title = st.text_input("المسمى", value=pos.title, key=f"pos_title_{pos.id}")
                dept_options = list(dept_labels.keys())
                cur_dept_label = next((l for l, i in dept_labels.items() if i == pos.department_id), dept_options[0])
                new_dept_label = st.selectbox(
                    "القسم", dept_options, index=dept_options.index(cur_dept_label), key=f"pos_dept_{pos.id}"
                )
                reports_options = {"— لا يتبع أحداً —": None} | {
                    v: k for k, v in pos_labels_base.items() if k != pos.id
                }
                reports_opt_keys = list(reports_options.keys())
                cur_reports_label = next(
                    (l for l, i in reports_options.items() if i == pos.reports_to_position_id), reports_opt_keys[0]
                )
                new_reports_label = st.selectbox(
                    "يتبع (Reports To)", reports_opt_keys, index=reports_opt_keys.index(cur_reports_label),
                    key=f"pos_reports_{pos.id}",
                )
                col1, col2 = st.columns(2)
                with col1:
                    new_required = st.number_input(
                        "العدد المطلوب", min_value=0, step=1, value=pos.required_headcount, key=f"pos_req_{pos.id}"
                    )
                with col2:
                    new_current = st.number_input(
                        "العدد الحالي", min_value=0, step=1, value=pos.current_headcount, key=f"pos_cur_{pos.id}"
                    )
                saved = st.form_submit_button("💾 حفظ", type="primary")
            if saved:
                try:
                    with get_db_session() as session:
                        OrganizationService(session).update_position(
                            pos.id,
                            title=new_title,
                            department_id=dept_labels[new_dept_label],
                            reports_to_position_id=reports_options[new_reports_label],
                            required_headcount=int(new_required),
                            current_headcount=int(new_current),
                        )
                    _invalidate_caches()
                    st.toast("تم الحفظ ✅")
                    st.rerun()
                except SmartATSError as exc:
                    st.error(str(exc))

            st.divider()
            confirm = st.checkbox("تأكيد حذف هذا المسمى", key=f"confirm_del_pos_{pos.id}")
            if st.button("🗑️ حذف المسمى", disabled=not confirm, key=f"del_pos_{pos.id}"):
                try:
                    with get_db_session() as session:
                        OrganizationService(session).delete_position(pos.id)
                    _invalidate_caches()
                    st.toast("تم الحذف 🗑️")
                    st.rerun()
                except SmartATSError as exc:
                    st.error(str(exc))


# ------------------------------------------------------------ الشجرة التنظيمية

def _render_chart_tab() -> None:
    departments = _cached_departments()
    positions = _cached_positions()

    if not departments and not positions:
        st.info("أضف أقساماً ومسميات وظيفية أولاً لعرض الهيكل التنظيمي.")
        return

    dept_children: dict[int | None, list] = {}
    for d in departments:
        dept_children.setdefault(d.parent_department_id, []).append(d)
    positions_by_dept: dict[int | None, list] = {}
    for p in positions:
        positions_by_dept.setdefault(p.department_id, []).append(p)
    positions_by_reports: dict[int | None, list] = {}
    for p in positions:
        positions_by_reports.setdefault(p.reports_to_position_id, []).append(p)

    def render_position(pos, depth: int) -> None:
        gap_note = f" — فجوة: {pos.gap}" if pos.gap > 0 else ""
        st.markdown("&nbsp;" * (depth * 4) + f"👤 **{pos.title}** ({pos.current_headcount}/{pos.required_headcount}){gap_note}")
        for child in positions_by_reports.get(pos.id, []):
            render_position(child, depth + 1)

    def render_department(dept, depth: int) -> None:
        st.markdown("&nbsp;" * (depth * 4) + f"🏢 **{dept.name}**")
        for pos in positions_by_dept.get(dept.id, []):
            if pos.reports_to_position_id is None:  # الجذور فقط هنا؛ التابعون يُرسمون recursively داخل render_position
                render_position(pos, depth + 1)
        for child_dept in dept_children.get(dept.id, []):
            render_department(child_dept, depth + 1)

    for root_dept in dept_children.get(None, []):
        render_department(root_dept, 0)
        st.divider()

    orphan_positions = [p for p in positions if p.department_id is None and p.reports_to_position_id is None]
    if orphan_positions:
        st.markdown("**🧑‍💼 مسميات بدون قسم**")
        for pos in orphan_positions:
            render_position(pos, 0)


# ------------------------------------------------------------ فجوة القوى العاملة

def _render_gap_tab() -> None:
    with get_db_session() as session:
        gaps = OrganizationService(session).workforce_gaps()

    if not gaps:
        st.success("لا توجد فجوات في القوى العاملة حالياً. كل المسميات مكتملة العدد.")
        return

    for pos in gaps:
        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{pos.title}**")
                st.caption(f"مطلوب: {pos.required_headcount} · حالي: {pos.current_headcount}")
            with col2:
                st.metric("الفجوة", pos.gap)

            if st.button(f"🔍 ابحث عن مرشحين لـ «{pos.title}»", key=f"find_{pos.id}"):
                with get_db_session() as session:
                    matches = CandidateService(session).search(pos.title)
                if matches:
                    for c in matches[:10]:
                        st.write(f"👤 {c.full_name} — {c.current_position or 'بدون مسمى'} — {c.email or '-'}")
                else:
                    st.info("لا يوجد مرشحون مطابقون لهذا المسمى في قاعدة البيانات حالياً.")


def render() -> None:
    st.header("🏢 الهيكل التنظيمي")

    tab_depts, tab_positions, tab_chart, tab_gap = st.tabs(
        ["🏢 الأقسام", "🧑‍💼 المسميات الوظيفية", "🌳 الشجرة التنظيمية", "⚠️ فجوة القوى العاملة"]
    )
    with tab_depts:
        _render_departments_tab()
    with tab_positions:
        _render_positions_tab()
    with tab_chart:
        _render_chart_tab()
    with tab_gap:
        _render_gap_tab()