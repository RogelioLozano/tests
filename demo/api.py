from typing import Optional
from demo.models import Item, User


_users: dict[int, User] = {}
_items: dict[int, Item] = {}
_next_user_id = 1
_next_item_id = 1


def create_user(name: str, email: str) -> User:
    global _next_user_id
    user = User(id=_next_user_id, name=name, email=email)
    _users[user.id] = user
    _next_user_id += 1
    return user


def get_user(user_id: int) -> Optional[User]:
    return _users.get(user_id)


def create_item(title: str, owner_id: int) -> Item:
    global _next_item_id
    if owner_id not in _users:
        raise ValueError(f"User {owner_id} does not exist")
    item = Item(id=_next_item_id, title=title, owner_id=owner_id)
    _items[item.id] = item
    _next_item_id += 1
    return item


def get_items_for_user(owner_id: int) -> list[Item]:
    return [item for item in _items.values() if item.owner_id == owner_id]
