from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.database import Base


class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True)  # Equipe meeting_id
    display_name = Column(String, nullable=True)
    start_on = Column(String, nullable=True)
    end_on = Column(String, nullable=True)
    synced_at = Column(DateTime, nullable=True)


class Rider(Base):
    __tablename__ = "riders"

    id = Column(Integer, primary_key=True)  # Equipe rider_id
    name = Column(String, nullable=True)
    club_name = Column(String, nullable=True)


class Start(Base):
    __tablename__ = "starts"

    id = Column(Integer, primary_key=True)  # Equipe start id
    meeting_id = Column(Integer, ForeignKey("meetings.id"), nullable=False, index=True)
    rider_id = Column(Integer, ForeignKey("riders.id"), nullable=False, index=True)
    horse_id = Column(Integer, nullable=True)
    horse_name = Column(String, nullable=True)
    class_section_id = Column(Integer, nullable=True)
    class_no = Column(Integer, nullable=True)
    competition_name = Column(String, nullable=True)
    start_no = Column(String, nullable=True)
    start_at = Column(DateTime(timezone=True), nullable=True)


class Photographed(Base):
    __tablename__ = "photographed"

    meeting_id = Column(Integer, ForeignKey("meetings.id"), primary_key=True)
    rider_id = Column(Integer, ForeignKey("riders.id"), primary_key=True)
    photographed_at = Column(DateTime(timezone=True), nullable=False)
