from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    games_played = db.Column(db.Integer, default=0)
    games_won = db.Column(db.Integer, default=0)

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(20), default='waiting')  # waiting, active, finished
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    current_player_id = db.Column(db.Integer)
    players = db.relationship('Player', backref='game', lazy=True)
    properties = db.relationship('Property', backref='game', lazy=True)

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    username = db.Column(db.String(80), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    balance = db.Column(db.Integer, default=1500)
    position = db.Column(db.Integer, default=0)
    in_jail = db.Column(db.Boolean, default=False)
    jail_turns = db.Column(db.Integer, default=0)
    get_out_of_jail_cards = db.Column(db.Integer, default=0)
    properties = db.relationship('Property', backref='owner', lazy=True)
    is_bankrupt = db.Column(db.Boolean, default=False)

class Property(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('player.id'))
    name = db.Column(db.String(50), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Integer, nullable=False)
    rent = db.Column(db.Integer, nullable=False)
    mortgage_value = db.Column(db.Integer, nullable=False)
    is_mortgaged = db.Column(db.Boolean, default=False)
    houses = db.Column(db.Integer, default=0)
    color_group = db.Column(db.String(20))
    house_price = db.Column(db.Integer, default=50)

class GameHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'))
    action = db.Column(db.String(50), nullable=False)
    details = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Trade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, accepted, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class TradeItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trade_id = db.Column(db.Integer, db.ForeignKey('trade.id'), nullable=False)
    type = db.Column(db.String(20))  # property, money, get_out_of_jail_card
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'))
    amount = db.Column(db.Integer)
    from_sender = db.Column(db.Boolean)  # True if item is from sender to receiver

class Auction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'), nullable=False)
    current_bid = db.Column(db.Integer, nullable=False)
    current_bidder_id = db.Column(db.Integer, db.ForeignKey('player.id'))
    status = db.Column(db.String(20), default='active')  # active, completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Card(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    type = db.Column(db.String(20))  # chance, community_chest
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    action = db.Column(db.String(50))  # move, pay, receive, jail, get_out_of_jail
    amount = db.Column(db.Integer)
    position = db.Column(db.Integer)