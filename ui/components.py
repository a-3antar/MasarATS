"""مكوّنات واجهة صغيرة قابلة لإعادة الاستخدام في كل الصفحات. لا تصل للقاعدة."""

import streamlit as st

from ui.navigation import go_to


def empty_state(
    icon: str,
    title: str,
    message: str,
    actions: list[tuple[str, str, dict | None]],
    key: str,
) -> None:
    """
    حالة فراغ تقترح الخطوة التالية بدل عبارة "لا توجد بيانات".
    actions: [(نص الزر، مفتاح الصفحة، قيم session_state إضافية أو None)] - الأول هو الإجراء الأساسي.
    key: بادئة فريدة لمفاتيح الأزرار (لأن الحالة قد تظهر أكثر من مرة في صفحة واحدة).
    """
    with st.container(border=True):
        st.markdown(f"### {icon} {title}")
        st.write(message)
        if not actions:
            return
        for index, (column, (label, page, state)) in enumerate(zip(st.columns(len(actions)), actions)):
            column.button(
                label, key=f"{key}_{index}", on_click=go_to, args=(page,), kwargs=state or {},
                type="primary" if index == 0 else "secondary", width="stretch",
            )
