"""UI catalogue only; descriptions do not imply future backends exist."""

from dataclasses import dataclass, replace
from enum import StrEnum


class Screen(StrEnum):
    HOME = "home"
    TODAY = "today"
    TASKS = "tasks"
    PROJECTS = "projects"
    CALENDAR = "calendar"
    REMINDERS = "reminders"
    AI = "ai"
    GOALS = "goals"
    FINANCE = "finance"
    HABITS = "habits"
    NOTES = "notes"
    MEMORY = "memory"
    REPORTS = "reports"
    SETTINGS = "settings"
    HELP = "help"


@dataclass(frozen=True, slots=True)
class Module:
    title: str
    description: str
    features: tuple[str, ...]
    available: bool = False


MODULES: dict[Screen, Module] = {
    Screen.TODAY: Module(
        "Today Dashboard",
        "Lịch trình và việc cần làm hôm nay.",
        ("Lịch trình trong ngày", "Công việc ưu tiên", "Lời nhắc sắp tới"),
    ),
    Screen.TASKS: Module(
        "Task Management",
        "Theo dõi những việc cần làm.",
        (
            "Danh sách công việc",
            "Bộ lọc trạng thái",
            "Ưu tiên và deadline",
            "Liên kết dự án",
            "Đánh dấu hoàn thành",
        ),
    ),
    Screen.PROJECTS: Module(
        "Project Management",
        "Theo dõi dự án và công việc liên quan.",
        ("Danh sách dự án", "Trạng thái dự án", "Tiến độ từ công việc"),
    ),
    Screen.CALENDAR: Module(
        "Calendar",
        "Xem các khung thời gian và lịch hẹn.",
        ("Lịch ngày và tuần", "Kiểm tra lịch trùng", "Khung giờ làm việc"),
    ),
    Screen.REMINDERS: Module(
        "Reminder Management",
        "Theo dõi thông báo nhắc việc.",
        ("Lời nhắc một lần", "Lời nhắc lặp lại", "Hoãn và hủy lời nhắc"),
    ),
    Screen.AI: Module(
        "AI Assistant",
        "Trò chuyện tự nhiên với NOVA qua DM.",
        ("Hỏi đáp bằng tiếng Việt", "Tra cứu việc và lịch", "Đề xuất có xác nhận"),
    ),
    Screen.GOALS: Module(
        "Goals",
        "Theo dõi mục tiêu cá nhân.",
        ("Danh sách mục tiêu", "Các mốc cần đạt", "Theo dõi tiến độ"),
    ),
    Screen.FINANCE: Module(
        "Finance",
        "Ghi chép thu chi cá nhân.",
        ("Ghi thu chi thủ công", "Phân loại giao dịch", "Tổng hợp chi tiêu"),
    ),
    Screen.HABITS: Module(
        "Habits",
        "Theo dõi thói quen hàng ngày.",
        ("Danh sách thói quen", "Đánh dấu theo ngày", "Theo dõi chuỗi ngày"),
    ),
    Screen.NOTES: Module(
        "Notes", "Lưu ghi chú cá nhân.", ("Danh sách ghi chú", "Tìm kiếm", "Phân loại ghi chú")
    ),
    Screen.MEMORY: Module(
        "Memory",
        "Quản lý thông tin được phép ghi nhớ.",
        ("Xem thông tin đã nhớ", "Nguồn và xác nhận", "Sửa hoặc xóa thông tin"),
    ),
    Screen.REPORTS: Module(
        "Reports",
        "Xem báo cáo dựa trên dữ liệu đã ghi nhận.",
        ("Báo cáo ngày", "Báo cáo tuần", "Tổng hợp tiến độ"),
    ),
    Screen.SETTINGS: Module(
        "Settings",
        "Xem cấu hình và chỉnh múi giờ.",
        (
            "Language",
            "Timezone",
            "Morning Briefing",
            "Daily Review",
            "Notification Preferences",
            "Owner Access",
        ),
        available=True,
    ),
}

QUICK_SCREENS = (Screen.TODAY, Screen.TASKS, Screen.PROJECTS, Screen.REMINDERS, Screen.AI)
for _screen in (Screen.TODAY, Screen.TASKS, Screen.PROJECTS, Screen.CALENDAR):
    MODULES[_screen] = replace(MODULES[_screen], available=True)
MORE_SCREENS = (
    Screen.CALENDAR,
    Screen.GOALS,
    Screen.FINANCE,
    Screen.HABITS,
    Screen.NOTES,
    Screen.MEMORY,
    Screen.REPORTS,
)
