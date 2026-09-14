from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    broker = Column(String(100), nullable=False)
    account_number = Column(String(100), nullable=False, unique=True)
    server = Column(String(255), nullable=True)
    login = Column(String(100), nullable=True)
    password = Column(String(255), nullable=True)
    status = Column(String(50), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)


class Symbol(Base):
    __tablename__ = "symbols"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    pip_value = Column(Float, nullable=True)
    lot_size = Column(Float, default=0.01)
    created_at = Column(DateTime, default=datetime.utcnow)


class TradeSignal(Base):
    __tablename__ = "trade_signals"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(50), nullable=False)
    signal_type = Column(String(20), nullable=False)  # BUY/SELL
    entry_price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    confidence = Column(Float, default=0.0)
    source = Column(String(50), default="system")
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
