import textwrap
from demo.api import create_item, create_user, get_items_for_user


def render_user_card(user_id: int) -> str:
    """Return a simple text card for a user and their items."""
    from demo.api import get_user

    user = get_user(user_id)
    if user is None:
        return f"[User {user_id} not found]"

    items = get_items_for_user(user_id)
    item_lines = "\n".join(f"  • {item.title}" for item in items) or "  (no items)"
    return textwrap.dedent(f"""\
        ┌─────────────────────────────┐
        │ User #{user.id}: {user.name:<18} │
        │ {user.email:<29} │
        ├─────────────────────────────┤
        │ Items:                      │
        {item_lines}
        └─────────────────────────────┘
    """)


def demo() -> None:
    alice = create_user("Alice", "alice@example.com")
    bob = create_user("Bob", "bob@example.com")

    create_item("Laptop", alice.id)
    create_item("Notebook", alice.id)
    create_item("Pen", bob.id)

    print(render_user_card(alice.id))
    print(render_user_card(bob.id))


if __name__ == "__main__":
    demo()
