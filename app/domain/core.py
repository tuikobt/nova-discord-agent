"""Validated immutable service inputs/results, independent of ORM and Discord.

Update inputs describe the entire editable record; nullable fields explicitly clear values.
"""

from dataclasses import dataclass, fields
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.domain.enums import EventStatus, ProjectStatus, TaskPriority, TaskStatus
from app.domain.errors import ValidationError
from app.domain.time import as_utc


def text_value(value: str, maximum: int, *, required: bool = True) -> str:
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise ValidationError(f"Nội dung không hợp lệ hoặc vượt quá {maximum} ký tự.")
    return value.strip()


def resource_id(value: str) -> str:
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except ValueError:
        raise ValidationError("ID bản ghi không hợp lệ.") from None
    return value


def enum_value(enum: type[StrEnum], value: str) -> str:
    try:
        return enum(value).value
    except (ValueError, TypeError):
        raise ValidationError("Trạng thái hoặc mức ưu tiên không hợp lệ.") from None


def normalize_common(data, *, label: str, maximum: int, enum: type[StrEnum]):
    object.__setattr__(data, label, text_value(getattr(data, label), maximum))
    object.__setattr__(data, "status", enum_value(enum, data.status))
    if data.description is not None:
        object.__setattr__(data, "description", text_value(data.description, 4000, required=False))


@dataclass(frozen=True, kw_only=True)
class ProjectData:
    name: str
    description: str | None = None
    status: str = ProjectStatus.ACTIVE
    deadline_at: datetime | None = None

    def __post_init__(self):
        normalize_common(self, label="name", maximum=200, enum=ProjectStatus)
        if self.deadline_at is not None:
            object.__setattr__(self, "deadline_at", as_utc(self.deadline_at))


@dataclass(frozen=True, kw_only=True)
class TaskData:
    title: str
    description: str | None = None
    status: str = TaskStatus.TODO
    priority: str = TaskPriority.MEDIUM
    project_id: str | None = None
    estimated_minutes: int | None = None
    due_at: datetime | None = None

    def __post_init__(self):
        normalize_common(self, label="title", maximum=250, enum=TaskStatus)
        object.__setattr__(self, "priority", enum_value(TaskPriority, self.priority))
        if self.project_id is not None:
            resource_id(self.project_id)
        if self.estimated_minutes is not None and (
            type(self.estimated_minutes) is not int or self.estimated_minutes <= 0
        ):
            raise ValidationError("Thời lượng ước tính phải là số nguyên dương.")
        if self.due_at is not None:
            object.__setattr__(self, "due_at", as_utc(self.due_at))


@dataclass(frozen=True, kw_only=True)
class EventData:
    title: str
    starts_at: datetime
    ends_at: datetime
    status: str = EventStatus.CONFIRMED
    is_fixed: bool = False
    task_id: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "title", text_value(self.title, 250))
        object.__setattr__(self, "status", enum_value(EventStatus, self.status))
        object.__setattr__(self, "starts_at", as_utc(self.starts_at))
        object.__setattr__(self, "ends_at", as_utc(self.ends_at))
        if self.ends_at <= self.starts_at:
            raise ValidationError("Giờ kết thúc phải sau giờ bắt đầu.")
        if type(self.is_fixed) is not bool:
            raise ValidationError("is_fixed phải là boolean.")
        if self.task_id is not None:
            resource_id(self.task_id)


@dataclass(frozen=True, kw_only=True)
class ProjectRecord(ProjectData):
    id: str
    owner_id: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, kw_only=True)
class TaskRecord(TaskData):
    id: str
    owner_id: str
    completed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, kw_only=True)
class EventRecord(EventData):
    id: str
    owner_id: str
    origin: str
    version: int
    created_at: datetime
    updated_at: datetime


def to_record(record_type, row):
    return record_type(**{field.name: getattr(row, field.name) for field in fields(record_type)})


def data_values(data) -> dict:
    return {field.name: getattr(data, field.name) for field in fields(data)}


@dataclass(frozen=True)
class Page[T]:
    items: tuple[T, ...]
    total: int
    page: int
    page_size: int


def pagination(page: int, page_size: int) -> None:
    if type(page) is not int or page < 0 or type(page_size) is not int or not 1 <= page_size <= 50:
        raise ValidationError("Trang phải >= 0; số mục mỗi trang từ 1 đến 50.")


@dataclass(frozen=True)
class ProjectProgress:
    done: int
    total: int

    @property
    def percent(self) -> float:
        return 100 * self.done / self.total if self.total else 0.0

    @property
    def description(self) -> str:
        return (
            "Tỷ lệ số lượng task đã xong, không tính task đã hủy."
            if self.total
            else "Chưa có nhiệm vụ."
        )
