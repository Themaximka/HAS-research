import csv
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st
from filelock import FileLock

TASKS = [
    "Автоматический ответ на электронные письма",
    "Анализ данных продаж",
    "Создание отчётов",
    "Подбор персонала",
    "Поддержка клиентов в чате",
]

RESULTS_PATH = Path("results.csv")
LOCK_PATH = Path("results.csv.lock")


def init_session() -> None:
    if "user_id" not in st.session_state:
        st.session_state.user_id = str(uuid.uuid4())

    for i in range(len(TASKS)):
        exclude_key = f"exclude_{i}"
        ability_key = f"ability_{i}"
        interaction_key = f"interaction_{i}"

        if exclude_key not in st.session_state:
            st.session_state[exclude_key] = False
        if ability_key not in st.session_state:
            st.session_state[ability_key] = 3
        if interaction_key not in st.session_state:
            st.session_state[interaction_key] = 3


def ensure_csv_exists() -> None:
    if RESULTS_PATH.exists():
        return
    with RESULTS_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["user_id", "timestamp", "task", "ability", "interaction"],
        )
        writer.writeheader()


def append_results(rows: list[dict]) -> None:
    ensure_csv_exists()
    with FileLock(str(LOCK_PATH)):
        with RESULTS_PATH.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["user_id", "timestamp", "task", "ability", "interaction"],
            )
            writer.writerows(rows)


def render_row(index: int, task: str) -> dict | None:
    exclude_key = f"exclude_{index}"
    ability_key = f"ability_{index}"
    interaction_key = f"interaction_{index}"
    is_excluded = st.session_state[exclude_key]

    col_task, col_ability, col_interaction = st.columns([3, 2, 2])

    with col_task:
        check_col, text_col = st.columns([1, 16])
        with check_col:
            st.checkbox("", key=exclude_key, label_visibility="collapsed")
        is_excluded = st.session_state[exclude_key]
        with text_col:
            if is_excluded:
                st.markdown(
                    f"<span style='text-decoration: line-through;'>{task}</span>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(task)

    with col_ability:
        ability = st.radio(
            " ",
            options=[1, 2, 3, 4, 5],
            horizontal=True,
            key=ability_key,
            disabled=is_excluded,
            label_visibility="collapsed",
        )

    with col_interaction:
        interaction = st.radio(
            "  ",
            options=[1, 2, 3, 4, 5],
            horizontal=True,
            key=interaction_key,
            disabled=is_excluded,
            label_visibility="collapsed",
        )

    if is_excluded:
        return None

    return {
        "task": task,
        "ability": ability,
        "interaction": interaction,
    }


def main() -> None:
    st.set_page_config(page_title="Опросник функциональных задач", layout="wide")
    init_session()

    st.title("Опросник функциональных задач")
    st.write(
        "Нажмите на название задачи, чтобы исключить её из оценки (строка будет зачёркнута). "
        "Для остальных задач выберите оценки от 1 до 5 по двум вопросам."
    )

    header_cols = st.columns([3, 2, 2])
    header_cols[0].markdown("**Задача (нажмите, чтобы исключить)**")
    header_cols[1].markdown("**Сможет ли ИИ-агент справиться? (1-5)**")
    header_cols[2].markdown("**Уровень взаимодействия человек-агент (1-5)**")

    current_answers = []
    for i, task in enumerate(TASKS):
        row = render_row(i, task)
        if row:
            current_answers.append(row)

    if st.button("Отправить результаты", type="primary"):
        if not current_answers:
            st.warning("Вы исключили все задачи. Оцените хотя бы одну строку перед отправкой.")
            return

        timestamp = datetime.now().isoformat(timespec="seconds")
        user_id = st.session_state.user_id
        rows_to_save = [
            {
                "user_id": user_id,
                "timestamp": timestamp,
                "task": answer["task"],
                "ability": answer["ability"],
                "interaction": answer["interaction"],
            }
            for answer in current_answers
        ]
        append_results(rows_to_save)
        st.success(f"Ответы сохранены. Ваш ID: {user_id}")


if __name__ == "__main__":
    main()
