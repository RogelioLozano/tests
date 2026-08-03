from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class User:
    id: int
    name: str
    email: str
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __repr__(self) -> str:
        return f"User(id={self.id}, name={self.name!r})"


@dataclass
class Item:
    id: int
    title: str
    owner_id: int
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __repr__(self) -> str:
        return f"Item(id={self.id}, title={self.title!r})"
