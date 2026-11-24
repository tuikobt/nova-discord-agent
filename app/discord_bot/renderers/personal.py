"""Human-readable personal settings and approvals, independent of persistence."""

from datetime import datetime

from app.discord_bot.renderers.core import safe
from app.domain.time import zone

DAYS = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ nhật")
MEMORY_KINDS = {"preference": "Sở thích", "routine": "Thói quen", "profile": "Thông tin về tôi"}
REPORT_NAMES = {"morning": "Bản tin sáng", "daily": "Tổng kết ngày", "weekly": "Tổng kết tuần"}
RUN_STATES = {
    "pending": "Chờ gửi",
    "claimed": "Đang chuẩn bị",
    "sent": "Đã gửi",
    "failed": "Chưa gửi được",
    "skipped": "Đã bỏ qua",
}


def when(value, timezone, fmt="%d/%m/%Y lúc %H:%M"):
    return datetime.fromisoformat(value).astimezone(zone(timezone)).strftime(fmt)


def source_name(source):
    if (source or "").startswith("dm:"):
        return "Bạn đã chia sẻ trong tin nhắn riêng"
    return "Bạn nhập trực tiếp trên Discord"


def work_summary(work):
    if not work.get("workdays"):
        return "Chưa thiết lập giờ làm. Bấm **Thiết lập giờ làm** để bắt đầu."
    return (
        ", ".join(DAYS[day] for day in work["workdays"])
        + f"\n{work['start']}–{work['end']} • nghỉ giữa các việc: {work['break_minutes']} phút"
    )


def policy_summary(policy):
    frequency = DAYS[policy["weekday"]] if policy["kind"] == "weekly" else "Mỗi ngày"
    destination = (
        "tin nhắn riêng với NOVA" if policy["target"] == "dm" else f"kênh <#{policy['channel_id']}>"
    )
    return (
        f"{'Đang bật' if policy['enabled'] else 'Đang tắt'} • {frequency}, {policy['time']}\n"
        f"Gửi đến {destination}."
        + (
            f" Nếu không gửi được tin riêng, dùng kênh dự phòng <#{policy['channel_id']}>."
            if policy["fallback"]
            else ""
        )
    )


def preview_lines(proposal):
    plan, lines = proposal["preview"], []
    kind, tz = plan["personal_kind"], plan["timezone"]
    lines.extend(
        ["ĐỀ XUẤT — CHƯA LƯU", f"Giờ theo {tz} • Duyệt trước {when(proposal['expires_at'], tz)}"]
    )
    if kind == "propose_schedule_tasks":
        lines.append("\nLịch làm việc đề xuất — mỗi khung giờ gắn với việc gốc:")
        for change in plan["changes"]:
            item = change["after"]
            duration = (
                datetime.fromisoformat(item["ends_at"]) - datetime.fromisoformat(item["starts_at"])
            ).total_seconds() / 60
            lines.extend(
                [
                    f"\n**{safe(item['title'], 1000)}**",
                    f"{when(item['starts_at'], tz)} → "
                    f"{when(item['ends_at'], tz, '%H:%M')} ({duration:g} phút)",
                ]
            )
    else:
        change = plan["changes"][0]
        before, after = change["before"], change["after"]
        if kind in {"propose_memory", "update_memory", "delete_memory"}:
            lines.append(
                "\n"
                + {
                    "propose_memory": "NOVA sẽ ghi nhớ:",
                    "update_memory": "Sửa điều đã ghi nhớ",
                    "delete_memory": "Xóa điều đã ghi nhớ",
                }[kind]
            )
            if before:
                lines.append("\nHiện tại:\n" + safe(before["content"], 4000))
            if kind == "delete_memory":
                lines.append(
                    "\nSau khi duyệt, NOVA sẽ không dùng thông tin này nữa. "
                    "Tin Discord và bản sao lưu cũ cần xóa riêng nếu muốn."
                )
            else:
                lines.extend(
                    [
                        "\nNội dung mới:\n" + safe(after["content"], 4000),
                        f"Loại: {MEMORY_KINDS[after['kind']]}",
                        "NOVA được dùng để hỗ trợ bạn: "
                        + ("Có" if after["use_for_ai"] else "Không"),
                    ]
                )
                lines.append(
                    "Nguồn: " + source_name(plan.get("source") or (before or {}).get("source"))
                )
        elif kind == "configure_work":
            lines.extend(
                [
                    "\nThay đổi giờ làm",
                    "\nHiện tại:\n" + work_summary(before),
                    "\nSau khi duyệt:\n" + work_summary(after),
                    "Gợi ý thông tin để ghi nhớ: "
                    + ("Bật" if after["memory_suggestions"] else "Tắt"),
                ]
            )
        elif kind == "configure_automation":
            report_kind = change["id"]
            lines.extend(
                [
                    "\n" + REPORT_NAMES[report_kind],
                    "\nHiện tại:\n" + policy_summary(before),
                    "\nSau khi duyệt:\n" + policy_summary(dict(kind=report_kind, **after)),
                    "NOVA tuân theo giờ yên lặng bạn đã cài.",
                ]
            )
    lines.append("\nĐọc xong rồi bấm **Duyệt** để lưu, hoặc **Hủy đề xuất**.")
    return lines
