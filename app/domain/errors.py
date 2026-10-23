"""Safe business errors; never expose SQL, private payloads, or exception strings."""


class DomainError(Exception):
    code = "domain_error"


class ValidationError(DomainError, ValueError):
    code = "validation_error"


class NotFoundError(DomainError):
    code = "not_found"

    def __init__(self):
        super().__init__("Không tìm thấy bản ghi trong dữ liệu của bạn.")


class StaleWriteError(DomainError):
    code = "stale_write"

    def __init__(self):
        super().__init__("Dữ liệu đã thay đổi. Hãy làm mới trước khi lưu lại.")


class StorageError(DomainError):
    code = "storage_error"

    def __init__(self):
        super().__init__("Chưa thể lưu hoặc đọc dữ liệu. Hãy thử lại.")


class DuplicateRequestError(DomainError):
    code = "duplicate_request"

    def __init__(self):
        super().__init__("Yêu cầu này đã được dùng với dữ liệu khác. Hãy mở phiên tạo mới.")


class ApprovalInvalidError(DomainError):
    code = "approval_invalid"

    def __init__(self):
        super().__init__("Xác nhận đã hết hạn, đã dùng hoặc dữ liệu đã đổi. Hãy xem lại đề xuất.")


class ConfirmationRequired(DomainError):
    code = "confirmation_required"

    def __init__(self, request):
        super().__init__("Thao tác cần được bạn xác nhận trước khi lưu.")
        self.request = request


class CalendarConflictError(ConfirmationRequired):
    code = "calendar_conflict"
