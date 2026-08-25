from sqlalchemy.orm import Session

from app import models


def get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.get(models.Setting, key)
    return row.value if row and row.value is not None else default


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(models.Setting, key)
    if row is None:
        row = models.Setting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()
