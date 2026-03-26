import csv
import uuid
from datetime import datetime
from pathlib import Path

import gspread
import streamlit as st
from filelock import FileLock
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError

POSITION_TASKS = {
    "Администратор базы данных": [
        "Модификация существующих баз данных и систем управления базами данных",
        "Применение мер безопасности для защиты информации в компьютерных файлах",
        "Установка обновлений программного обеспечения системы управления базами данных",
        "Назначение пользователей и уровней доступа для каждого сегмента базы данных",
        "Тестирование изменений в приложениях или системах баз данных",
        "Тестирование, исправление ошибок и внесение необходимых изменений",
        "Обучение пользователей и ответы на вопросы",
    ],
    "Data Scientists": [
        "Анализ, обработка и преобразование больших массивов данных с помощью статистического ПО",
        "Применение алгоритмов отбора признаков для прогноза целевых результатов",
        "Применение методов выборки для обследований или использование методов полного учета",
        "Очистка исходных данных и их обработка статистическим ПО",
        "Сравнение моделей по статистическим метрикам качества",
    ],
}

RESULTS_PATH = Path("results.csv")
LOCK_PATH = Path("results.csv.lock")
CSV_FIELDS = ["user_id", "timestamp", "position", "task", "ability", "interaction"]
GSHEET_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def init_session(position_key: str, tasks: list[str]) -> None:
    if "user_id" not in st.session_state:
        st.session_state.user_id = str(uuid.uuid4())

    for i in range(len(tasks)):
        exclude_key = f"exclude_{position_key}_{i}"
        ability_key = f"ability_{position_key}_{i}"
        interaction_key = f"interaction_{position_key}_{i}"

        if exclude_key not in st.session_state:
            st.session_state[exclude_key] = False
        if ability_key not in st.session_state:
            st.session_state[ability_key] = 3
        if interaction_key not in st.session_state:
            st.session_state[interaction_key] = 3


def ensure_csv_schema_locked() -> None:
    if not RESULTS_PATH.exists():
        with RESULTS_PATH.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
        return

    with RESULTS_PATH.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        existing_fields = reader.fieldnames or []
        rows = list(reader)

    if existing_fields == CSV_FIELDS:
        return

    migrated = []
    for row in rows:
        migrated.append(
            {
                "user_id": row.get("user_id", ""),
                "timestamp": row.get("timestamp", ""),
                "position": row.get("position", ""),
                "task": row.get("task", ""),
                "ability": row.get("ability", ""),
                "interaction": row.get("interaction", ""),
            }
        )

    with RESULTS_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(migrated)


def append_results_csv(rows: list[dict]) -> None:
    with FileLock(str(LOCK_PATH)):
        ensure_csv_schema_locked()
        with RESULTS_PATH.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writerows(rows)


@st.cache_resource
def get_gsheet_client():
    if "gcp_service_account" not in st.secrets:
        return None
    service_account = dict(st.secrets["gcp_service_account"])
    required = ["project_id", "private_key", "client_email", "token_uri"]
    missing = [key for key in required if not service_account.get(key)]
    if missing:
        raise ValueError(f"В gcp_service_account отсутствуют поля: {', '.join(missing)}")
    service_account["private_key"] = service_account.get("private_key", "").replace("\\n", "\n")
    creds = Credentials.from_service_account_info(
        service_account,
        scopes=GSHEET_SCOPES,
    )
    return gspread.authorize(creds)


def append_results_to_gsheet(rows: list[dict]) -> tuple[bool, str]:
    spreadsheet_id = st.secrets.get("google_sheet_id", "").strip()
    worksheet_name = st.secrets.get("google_sheet_worksheet", "results").strip()
    if not spreadsheet_id:
        return False, "В secrets не задан google_sheet_id."

    client = get_gsheet_client()
    if client is None:
        return False, "В secrets не задан блок gcp_service_account."

    try:
        spreadsheet = client.open_by_key(spreadsheet_id)
    except gspread.SpreadsheetNotFound:
        return False, (
            "Таблица не найдена или нет доступа. Проверьте google_sheet_id и доступ Editor "
            "для service account (client_email)."
        )
    except PermissionError:
        return False, (
            "Нет прав доступа к Google Sheets. Откройте таблицу и выдайте права Editor "
            "для service account (client_email из secrets)."
        )
    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        try:
            worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=2000, cols=12)
        except PermissionError:
            return False, (
                "Нет прав на создание листа в таблице. Выдайте service account роль Editor."
            )

    existing_header = worksheet.row_values(1)
    if existing_header != CSV_FIELDS:
        worksheet.update("A1:F1", [CSV_FIELDS])

    values = [[row.get(field, "") for field in CSV_FIELDS] for row in rows]
    try:
        worksheet.append_rows(values, value_input_option="RAW")
    except APIError as exc:
        return False, f"Google API Error: {exc}"
    except PermissionError:
        return False, (
            "Нет прав на запись в таблицу. Выдайте service account роль Editor."
        )
    sheet_link = f"{spreadsheet.url}#gid={worksheet.id}"
    return True, f"Лист: {worksheet.title}. Ссылка: {sheet_link}"


def render_row(position_key: str, index: int, task: str) -> dict | None:
    exclude_key = f"exclude_{position_key}_{index}"
    ability_key = f"ability_{position_key}_{index}"
    interaction_key = f"interaction_{position_key}_{index}"
    is_excluded = st.session_state[exclude_key]

    with st.container(border=True):
        check_col, text_col = st.columns([1, 16], vertical_alignment="center")
        with check_col:
            st.checkbox("", key=exclude_key, label_visibility="collapsed")
        is_excluded = st.session_state[exclude_key]
        with text_col:
            if is_excluded:
                st.markdown(
                    f"<div style='text-decoration: line-through; margin-top: 0.1rem;'>{task}</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(f"<div style='margin-top: 0.1rem;'>{task}</div>", unsafe_allow_html=True)

        ability = st.radio(
            "Сможет ли ИИ-агент справиться? (1-5)",
            options=[1, 2, 3, 4, 5],
            horizontal=True,
            key=ability_key,
            disabled=is_excluded,
        )

        interaction = st.radio(
            "Уровень взаимодействия человек-агент (1-5)",
            options=[1, 2, 3, 4, 5],
            horizontal=True,
            key=interaction_key,
            disabled=is_excluded,
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

    st.title("Опросник функциональных задач")
    st.write(
        "Выберите должность, затем оцените только релевантные задачи. "
        "Чтобы исключить задачу, снимите галочку: строка будет зачеркнута и не попадет в результаты."
    )
    st.markdown(
        """
        <style>
          .block-container {padding-top: 1.2rem; padding-bottom: 4rem;}
          @media (max-width: 768px) {
            .block-container {padding-left: 0.8rem; padding-right: 0.8rem;}
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    positions = list(POSITION_TASKS.keys())
    selected_position = st.selectbox("Ваша должность", positions)
    tasks = POSITION_TASKS[selected_position]
    position_key = str(positions.index(selected_position))

    init_session(position_key, tasks)

    st.markdown("**Задачи для оценки**")

    current_answers = []
    for i, task in enumerate(tasks):
        row = render_row(position_key, i, task)
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
                "position": selected_position,
                "task": answer["task"],
                "ability": answer["ability"],
                "interaction": answer["interaction"],
            }
            for answer in current_answers
        ]

        try:
            saved_to_gsheet, reason = append_results_to_gsheet(rows_to_save)
        except Exception as exc:
            details = str(exc).strip() or repr(exc)
            saved_to_gsheet, reason = False, f"{type(exc).__name__}: {details}"

        if saved_to_gsheet:
            st.success(
                f"Ответы сохранены в Google Sheets. Ваш ID: {user_id}. {reason}"
            )
        else:
            if not reason.strip():
                reason = "Неизвестная ошибка инициализации Google Sheets."
            append_results_csv(rows_to_save)
            st.warning(
                "Не удалось сохранить в Google Sheets, ответы записаны в локальный CSV. "
                f"Причина: {reason}"
            )


if __name__ == "__main__":
    main()
