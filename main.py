from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from models import db, User, Game, Player, Property, Trade, TradeItem, Auction, Card, GameHistory
from flasgger import Swagger
import random
from datetime import datetime
import json
import os

app = Flask(__name__)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///monopoly.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = 'very_secret-key'
app.config['SWAGGER'] = {
    'title': 'Monopoly API',
    'uiversion': 3,
    'doc_expansion': 'none',
    'specs_route': '/apidocs/'
}


app.config['CORS_HEADERS'] = 'Content-Type'
app.config['CORS_SUPPORTS_CREDENTIALS'] = True
app.config['CORS_EXPOSE_HEADERS'] = ['Content-Type', 'Authorization']
app.config['CORS_MAX_AGE'] = 3600
app.config['CORS_ORIGINS'] = [
    '*'
]
CORS(app)

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)
jwt = JWTManager(app)
swagger = Swagger(app)

# set JWT token expiration time to 1 week
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = 60 * 60 * 24 * 7


# Helper functions
def record_game_history(game_id, player_id, action, details=None):
    history = GameHistory(
        game_id=game_id,
        player_id=player_id,
        action=action,
        details=details
    )
    db.session.add(history)
    db.session.commit()

def transfer_funds(sender, receiver, amount):
    if sender.balance < amount:
        return False
    sender.balance -= amount
    if receiver:  # If receiver is None, money goes to bank
        receiver.balance += amount
    return True

def calculate_rent(property, game_id):
    if not property.owner_id or property.is_mortgaged:
        return 0
        
    base_rent = property.rent
    
    # Check if owner owns all properties in the color group
    color_group_properties = Property.query.filter_by(
        game_id=game_id,
        color_group=property.color_group
    ).all()
    
    owns_all = all(p.owner_id == property.owner_id for p in color_group_properties)
    
    if owns_all:
        if property.houses == 0:
            return base_rent * 2  # Double rent for complete color set
        elif property.houses == 1:
            return property.rent_with_1_house
        elif property.houses == 2:
            return property.rent_with_2_houses
        elif property.houses == 3:
            return property.rent_with_3_houses
        elif property.houses == 4:
            return property.rent_with_hotel
    
    return base_rent

def initialize_properties(game_id):
    # Standard Monopoly properties
    properties_file_path = os.path.join(os.path.dirname(__file__), 'properties.json')
    with open(properties_file_path, 'r') as file:
        properties = json.load(file)
    print(properties)
    
    for prop in properties:
        new_prop = Property(
            game_id=game_id,
            name=prop['name'],
            position=prop['position'],
            price=prop.get('price', 0),
            rent=prop.get('rent', 0),
            #rent_with_1_house=prop.get('rent_with_1_house', None),
            #rent_with_2_houses=prop.get('rent_with_2_houses', None),
            #rent_with_3_houses=prop.get('rent_with_3_houses', None),
            #rent_with_hotel=prop.get('rent_with_hotel', None),
            mortgage_value=prop.get('mortgage_value', 0),
            color_group=prop.get('color_group', ''),
            house_price=prop.get('house_price', 0)
        )
        db.session.add(new_prop)
    db.session.commit()

@app.route('/')
def index():
    return redirect('/apidocs')

### User Management Endpoints ###
@app.route('/users/register', methods=['POST'])
def register():
    """
    Register a new user.
    ---
    tags:
      - Users
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            username:
              type: string
            password:
              type: string
    responses:
      201:
        description: User registered successfully
        schema:
          type: object
          properties:
            message:
              type: string
            user_id:
              type: integer
      400:
        description: Username already exists
    """
    data = request.get_json()
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'message': 'Username already exists'}), 400
        
    new_user = User(username=data['username'], password=data['password'])
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'message': 'User registered successfully', 'user_id': new_user.id}), 201

@app.route('/users/login', methods=['POST'])
def login():
    """
    Authenticate a user.
    ---
    tags:
      - Users
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            username:
              type: string
            password:
              type: string
    responses:
      200:
        description: Login successful
        schema: 
          type: object
          properties:
            token:
              type: string
      401:
        description: Invalid credentials
    """
    data = request.get_json()
    user = User.query.filter_by(username=data['username']).first()
    
    if not user or user.password != data['password']:
        return jsonify({'message': 'Invalid credentials'}), 401

    access_token = create_access_token(identity=str(user.id))
    return jsonify({'token': access_token}), 200

@app.route('/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    """
    Get user details.
    ---
    tags:
      - Users
    parameters:
      - in: path
        name: user_id
        required: true
        type: integer
    responses:
      200:
        description: User details
        schema:
          type: object
          properties:
            id:
              type: integer
            username:
              type: string
            games_played:
              type: integer
            games_won:
              type: integer
      404:
        description: User not found
    """
    user = User.query.get(user_id)
    if not user:
        return jsonify({'message': 'User not found'}), 404
        
    return jsonify({
        'id': user.id,
        'username': user.username,
        'games_played': user.games_played,
        'games_won': user.games_won
    }), 200

### Game Management Endpoints ###
@app.route('/games', methods=['GET'])
def get_all_games():
  """
  Get all games, optionally filtered by status.
  ---
  tags:
    - Game
  parameters:
    - in: query
      name: status
      required: false
      type: string
      description: Filter games by status (e.g., 'waiting', 'active', 'finished')
  responses:
    200:
      description: List of games
      schema:
        type: array
        items:
          type: object
          properties:
            id:
              type: integer
            status:
              type: string
            current_player_id:
              type: integer
            players:
              type: array
              items:
                type: object
                properties:
                  user_id:
                    type: integer
                  username:
                    type: string
            placements:
              type: array
              items:
                type: object
                properties:
                  player_id:
                    type: integer
                  placement:
                    type: integer
            player_count:
              type: integer
  """
  status = request.args.get('status')
  if status:
    games = Game.query.filter_by(status=status).all()
  else:
    games = Game.query.all()
  return jsonify([{
    'id': game.id,
    'status': game.status,
    'current_player_id': game.current_player_id,
    'players': [
        {
            'user_id': player.user_id,
            'username': player.username
        } for player in game.players
    ],
    'placements': [
      {
        'player_id': player.id,
        'placement': idx + 1
      }
      for idx, player in enumerate(
        sorted(
          game.players,
          key=lambda p: p.balance + sum(
            prop.price for prop in Property.query.filter_by(owner_id=p.id).all()
          ),
          reverse=True
        )
      )
    ] if game.status == 'finished' else [],
    'max_players': game.max_players,
    'player_count': len(game.players)
  } for game in games]), 200


@app.route('/games/create', methods=['POST'])
@jwt_required()
def create_game():
    """
    Create a new game.
    ---
    tags:
      - Game
    parameters:
      - in: query
        name: max_players
        required: false
        type: integer
        description: Maximum number of players
    responses:
      201:
        description: Game created
        schema:
          type: object
          properties:
            message:
              type: string
            game_id:
              type: integer
    """
    max_players = request.args.get('max_players', default=4, type=int)
    user_id = get_jwt_identity()
    user = User.query.get(user_id)  # Fetch the user from the database
    new_game = Game(max_players=max_players)
    db.session.add(new_game)
    db.session.flush()  # Flush to get the ID before commit
    new_player = Player(user_id=user_id, username=user.username, game_id=new_game.id, balance=1500)
    db.session.add(new_player)
    
    db.session.commit()
    return jsonify({
        'message': 'Game created',
        'game_id': new_game.id,
        'player_id': new_player.id
    }), 201

@app.route('/games/<int:game_id>/join', methods=['POST'])
@jwt_required()
def join_game(game_id):
    """
    Join an existing game.
    ---
    tags:
      - Game
    parameters:
      - in: path
        name: game_id
        required: true
        type: integer
    responses:
      200:
        description: Player joined successfully
        schema:
          type: object
          properties:
            message:
              type: string
            player_id:
              type: integer
      404:
        description: Game not found
        schema:
          type: object
          properties:
            message:
              type: string
      400:
        description: Game already started or already in game
        schema:
          type: object
          properties:
            message:
              type: string
    """
    user_id = get_jwt_identity()
    user = User.query.get(user_id)  # Fetch the user from the database
    
    if not user:
      return jsonify({'message': 'User not found'}), 404
    
    game = Game.query.get(game_id)
    
    if not game:
      return jsonify({'message': 'Game not found'}), 404
      
    if game.status != 'waiting':
      return jsonify({'message': 'Game already started'}), 400
      
    # Check if user is already in the game
    existing_player = Player.query.filter_by(user_id=user_id, game_id=game_id).first()
    if existing_player:
      return jsonify({'message': 'Already in game'}), 400
    
    # Check if max players reached
    if len(game.players) >= game.max_players:
      return jsonify({'message': 'Max players reached'}), 400
    
    new_player = Player(user_id=user_id, username=user.username, game_id=game.id, balance=1500)
    db.session.add(new_player)
    db.session.commit()
    return jsonify({'message': 'Player joined', 'player_id': new_player.id}), 200

@app.route('/games/<int:game_id>/start', methods=['POST'])
@jwt_required()
def start_game(game_id):
    """
    Start a game.
    ---
    tags:
      - Game
    parameters:
      - in: path
        name: game_id
        required: true
        type: integer
    responses:
      200:
        description: Game started
      404:
        description: Game not found
      400:
        description: Not enough players
    """
    user_id = get_jwt_identity()
    game = Game.query.get(game_id)
    
    if not game:
        return jsonify({'message': 'Game not found'}), 404
        
    # Verify requesting user is in the game
    player = Player.query.filter_by(user_id=user_id, game_id=game_id).first()
    if not player:
        return jsonify({'message': 'Not in game'}), 403
        
    # Check if game can be started (minimum 2 players)
    players = Player.query.filter_by(game_id=game_id).count()
    if players < 2:
        return jsonify({'message': 'Need at least 2 players to start'}), 400
        
    # Initialize game properties if not already done
    if not game.properties:
        initialize_properties(game_id)
        
    game.status = 'active'
    game.current_player_id = player.id  # Let the creator go first
    db.session.commit()
    
    record_game_history(game_id, None, 'game_started')
    return jsonify({'message': 'Game started'}), 200

@app.route('/games/<int:game_id>', methods=['GET'])
@jwt_required()
def get_game_state(game_id):
    """
    Get game state.
    ---
    tags:
      - Game
    parameters:
      - in: path
        name: game_id
        required: true
        type: integer
    responses:
      200:
        description: Game state
        schema:
          type: object
          properties:
            status:
              type: string
            current_player_id:
              type: integer
            max_players:
              type: integer
            players:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  user_id:
                    type: integer
                  balance:
                    type: integer
                  position:
                    type: integer
                  in_jail:
                    type: boolean
                  is_bankrupt:
                    type: boolean
            properties:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  name:
                    type: string
                  position:
                    type: integer
                  price:
                    type: integer
                  owner_id:
                    type: integer
                  is_mortgaged:
                    type: boolean
                  houses:
                    type: integer
                  color_group:
                    type: string
      404:
        description: Game not found
    """
    game = Game.query.get(game_id)
    if not game:
        return jsonify({'message': 'Game not found'}), 404
        
    players = Player.query.filter_by(game_id=game_id).all()
    properties = Property.query.filter_by(game_id=game_id).all()
    
    return jsonify({
        'status': game.status,
        'current_player_id': game.current_player_id,
        'max_players': game.max_players,
        'players': [{
            'id': p.id,
            'user_id': p.user_id,
            'balance': p.balance,
            'position': p.position,
            'in_jail': p.in_jail,
            'is_bankrupt': p.is_bankrupt
        } for p in players],
        'properties': [{
            'id': prop.id,
            'name': prop.name,
            'position': prop.position,
            'price': prop.price,
            'owner_id': prop.owner_id,
            'is_mortgaged': prop.is_mortgaged,
            'houses': prop.houses,
            'color_group': prop.color_group
        } for prop in properties]
    }), 200

### Gameplay Endpoints ###
@app.route('/games/<int:game_id>/roll', methods=['POST'])
@jwt_required()
def roll_dice(game_id):
    """
    Roll dice and move player.
    ---
    tags:
      - Game
    parameters:
      - in: path
        name: game_id
        required: true
        type: integer
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            player_id:
              type: integer
    responses:
      200:
        description: Dice rolled and player moved
        schema:
          type: object
          properties:
            dice:
              type: array
              items:
                type: integer
            new_position:
              type: integer
            is_double:
              type: boolean
            property:
              type: object
              properties:
                id:
                  type: integer
                name:
                  type: string
                price:
                  type: integer
                can_buy:
                  type: boolean
                owner_id:
                  type: integer
                rent_due:
                  type: integer
      403:
        description: Not your turn
      404:
        description: Game or player not found
    """
    user_id = get_jwt_identity()
    game = Game.query.get(game_id)
    player = Player.query.filter_by(id=request.json['player_id'], game_id=game_id).first()
    
    if not game or not player:
        return jsonify({'message': 'Game or player not found'}), 404
        
    if game.current_player_id != player.id:
        return jsonify({'message': 'Not your turn'}), 403
        
    # Roll dice
    dice1 = random.randint(1, 6)
    dice2 = random.randint(1, 6)
    total = dice1 + dice2
    double = dice1 == dice2
    
    # Handle jail
    if player.in_jail:
        if double:
            player.in_jail = False
            player.jail_turns = 0
        else:
            player.jail_turns += 1
            if player.jail_turns >= 3:
                player.in_jail = False
                player.jail_turns = 0
                if not transfer_funds(player, None, 50):  # Pay $50 to get out
                    return jsonify({'message': 'Cannot pay to get out of jail'}), 400
            db.session.commit()
            return jsonify({
                'message': 'Still in jail',
                'dice': [dice1, dice2],
                'jail_turns': player.jail_turns
            }), 200
    
    # Move player
    new_position = (player.position + total) % 40
    player.position = new_position
    
    # Check for passing Go
    if (player.position + total) >= 40:
        player.balance += 200
        record_game_history(game_id, player.id, 'passed_go', 'Received $200')
    
    # Determine next player
    if not double:
        players = Player.query.filter_by(game_id=game_id, is_bankrupt=False).order_by(Player.id).all()
        current_index = next((i for i, p in enumerate(players) if p.id == player.id), 0)
        next_index = (current_index + 1) % len(players)
        game.current_player_id = players[next_index].id
    
    db.session.commit()
    
    # Check property at new position
    property = Property.query.filter_by(game_id=game_id, position=new_position).first()
    response = {
        'dice': [dice1, dice2],
        'new_position': new_position,
        'is_double': double
    }
    
    if property:
        if property.owner_id is None:
            response.update({
                'property': {
                    'id': property.id,
                    'name': property.name,
                    'price': property.price,
                    'can_buy': player.balance >= property.price
                }
            })
        elif property.owner_id != player.id:
            rent = calculate_rent(property, game_id)
            response.update({
                'property': {
                    'id': property.id,
                    'name': property.name,
                    'owner_id': property.owner_id,
                    'rent_due': rent
                }
            })
    
    return jsonify(response), 200

### Property Endpoints ###
@app.route('/games/<int:game_id>/property/<int:property_id>/buy', methods=['POST'])
@jwt_required()
def buy_property(game_id, property_id):
    """
    Buy a property.
    ---
    tags:
      - Property
    parameters:
      - in: path
        name: game_id
        required: true
        type: integer
      - in: path
        name: property_id
        required: true
        type: integer
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            player_id:
              type: integer
    responses:
      200:
        description: Property purchased
        schema:
          type: object
          properties:
            message:
              type: string
      400:
        description: Cannot buy property
      404:
        description: Property or player not found
    """
    user_id = get_jwt_identity()
    property = Property.query.filter_by(id=property_id, game_id=game_id).first()
    player = Player.query.filter_by(id=request.json['player_id'], game_id=game_id).first()
    
    if not property or not player:
        return jsonify({'message': 'Property or player not found'}), 404
        
    if property.owner_id:
        return jsonify({'message': 'Property already owned'}), 400
        
    if player.balance < property.price:
        return jsonify({'message': 'Insufficient funds'}), 400
        
    if player.position != property.position:
        return jsonify({'message': 'Not on this property'}), 400
        
    player.balance -= property.price
    property.owner_id = player.id
    db.session.commit()
    
    record_game_history(game_id, player.id, 'property_purchased', property.name)
    return jsonify({'message': 'Property purchased'}), 200

@app.route('/games/<int:game_id>/property/<int:property_id>/mortgage', methods=['POST'])
@jwt_required()
def mortgage_property(game_id, property_id):
    """
    Mortgage a property.
    ---
    tags:
      - Property
    parameters:
      - in: path
        name: game_id
        required: true
        type: integer
      - in: path
        name: property_id
        required: true
        type: integer
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            player_id:
              type: integer
    responses:
      200:
        description: Property mortgaged
        schema:
          type: object
          properties:
            message:
              type: string
      400:
        description: Cannot mortgage property
      404:
        description: Property or player not found
    """
    user_id = get_jwt_identity()
    property = Property.query.filter_by(id=property_id, game_id=game_id).first()
    player = Player.query.filter_by(id=request.json['player_id'], game_id=game_id).first()
    
    if not property or not player:
        return jsonify({'message': 'Property or player not found'}), 404
        
    if property.owner_id != player.id:
        return jsonify({'message': 'You do not own this property'}), 403
        
    if property.is_mortgaged:
        return jsonify({'message': 'Property already mortgaged'}), 400
        
    if property.houses > 0:
        return jsonify({'message': 'Must sell all houses first'}), 400
        
    property.is_mortgaged = True
    player.balance += property.mortgage_value
    db.session.commit()
    
    record_game_history(game_id, player.id, 'property_mortgaged', property.name)
    return jsonify({'message': 'Property mortgaged'}), 200

@app.route('/games/<int:game_id>/property/<int:property_id>/unmortgage', methods=['POST'])
@jwt_required()
def unmortgage_property(game_id, property_id):
    """
    Unmortgage a property.
    ---
    tags:
      - Property
    parameters:
      - in: path
        name: game_id
        required: true
        type: integer
      - in: path
        name: property_id
        required: true
        type: integer
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            player_id:
              type: integer
    responses:
      200:
        description: Property unmortgaged
        schema:
          type: object
          properties:
            message:
              type: string
      400:
        description: Cannot unmortgage property
      404:
        description: Property or player not found
    """
    user_id = get_jwt_identity()
    property = Property.query.filter_by(id=property_id, game_id=game_id).first()
    player = Player.query.filter_by(id=request.json['player_id'], game_id=game_id).first()
    
    if not property or not player:
        return jsonify({'message': 'Property or player not found'}), 404
        
    if property.owner_id != player.id:
        return jsonify({'message': 'You do not own this property'}), 403
        
    if not property.is_mortgaged:
        return jsonify({'message': 'Property is not mortgaged'}), 400
        
    unmortgage_cost = int(property.mortgage_value * 1.1)  # 10% interest
    if player.balance < unmortgage_cost:
        return jsonify({'message': 'Insufficient funds to unmortgage'}), 400
        
    property.is_mortgaged = False
    player.balance -= unmortgage_cost
    db.session.commit()
    
    record_game_history(game_id, player.id, 'property_unmortgaged', property.name)
    return jsonify({'message': 'Property unmortgaged'}), 200

@app.route('/games/<int:game_id>/property/<int:property_id>/build', methods=['POST'])
@jwt_required()
def build_house(game_id, property_id):
    """
    Build a house on a property.
    ---
    tags:
      - Property
    parameters:
      - in: path
        name: game_id
        required: true
        type: integer
      - in: path
        name: property_id
        required: true
        type: integer
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            player_id:
              type: integer
    responses:
      200:
        description: House built
        schema: 
          type: object
          properties:
            message:
              type: string
      400:
        description: Cannot build house
      404:
        description: Property or player not found
    """
    user_id = get_jwt_identity()
    property = Property.query.filter_by(id=property_id, game_id=game_id).first()
    player = Player.query.filter_by(id=request.json['player_id'], game_id=game_id).first()
    
    if not property or not player:
        return jsonify({'message': 'Property or player not found'}), 404
        
    if player.user_id != user_id:
        return jsonify({'message': 'Cannot build for another player'}), 403
        
    if property.owner_id != player.id:
        return jsonify({'message': 'You do not own this property'}), 403
        
    if property.is_mortgaged:
        return jsonify({'message': 'Cannot build on mortgaged property'}), 400
        
    # Check if player owns all properties in the color group
    color_group_properties = Property.query.filter_by(
        game_id=game_id,
        color_group=property.color_group
    ).all()
    
    for prop in color_group_properties:
        if prop.owner_id != player.id:
            return jsonify({'message': 'You must own all properties in this color group'}), 400
    
    if property.houses >= 4:
        return jsonify({'message': 'Maximum houses already built'}), 400
        
    if player.balance < property.house_price:
        return jsonify({'message': 'Insufficient funds'}), 400
        
    player.balance -= property.house_price
    property.houses += 1
    db.session.commit()
    
    record_game_history(game_id, player.id, 'house_built', property.name)
    return jsonify({'message': 'House built'}), 200

@app.route('/games/<int:game_id>/property/<int:property_id>/sell_house', methods=['POST'])
@jwt_required()
def sell_house(game_id, property_id):
    """
    Sell a house from a property.
    ---
    tags:
      - Property
    parameters:
      - in: path
        name: game_id
        required: true
        type: integer
      - in: path
        name: property_id
        required: true
        type: integer
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            player_id:
              type: integer
    responses:
      200:
        description: House sold
        schema:
          type: object
          properties:
            message:
              type: string
            amount:
              type: integer
      400:
        description: Cannot sell house
      404:
        description: Property or player not found
    """
    user_id = get_jwt_identity()
    property = Property.query.filter_by(id=property_id, game_id=game_id).first()
    player = Player.query.filter_by(id=request.json['player_id'], game_id=game_id).first()
    
    if not property or not player:
        return jsonify({'message': 'Property or player not found'}), 404
        
    if player.user_id != user_id:
        return jsonify({'message': 'Cannot sell for another player'}), 403
        
    if property.owner_id != player.id:
        return jsonify({'message': 'You do not own this property'}), 403
        
    if property.houses <= 0:
        return jsonify({'message': 'No houses to sell'}), 400
        
    # Check if selling would make houses uneven
    color_group_properties = Property.query.filter_by(
        game_id=game_id,
        color_group=property.color_group
    ).all()
    
    for prop in color_group_properties:
        if prop.id != property.id and prop.houses > property.houses - 1:
            return jsonify({'message': 'Cannot sell - would make houses uneven'}), 400
    
    sell_price = property.house_price // 2
    player.balance += sell_price
    property.houses -= 1
    db.session.commit()
    
    record_game_history(game_id, player.id, 'house_sold', property.name)
    return jsonify({'message': 'House sold', 'amount': sell_price}), 200

### Trade Endpoints ###
@app.route('/games/<int:game_id>/trade', methods=['POST'])
@jwt_required()
def create_trade(game_id):
    """
    Create a new trade offer.
    ---
    tags:
      - Trade
    parameters:
      - in: path
        name: game_id
        required: true
        type: integer
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            sender_id:
              type: integer
            receiver_id:
              type: integer
            offer:
              type: array
              items:
                type: object
                properties:
                  type:
                    type: string
                    enum: [property, money, get_out_of_jail_card]
                  property_id:
                    type: integer
                  amount:
                    type: integer
            request:
              type: array
              items:
                type: object
                properties:
                  type:
                    type: string
                    enum: [property, money, get_out_of_jail_card]
                  property_id:
                    type: integer
                  amount:
                    type: integer
    responses:
      201:
        description: Trade created
        schema:
          type: object
          properties:
            message:
              type: string
            trade_id:
              type: integer
      400:
        description: Invalid trade
      404:
        description: Game or player not found
    """
    user_id = get_jwt_identity()
    data = request.get_json()
    
    # Verify game and players exist and are in the same game
    game = Game.query.get(game_id)
    sender = Player.query.filter_by(id=data['sender_id'], game_id=game_id).first()
    receiver = Player.query.filter_by(id=data['receiver_id'], game_id=game_id).first()
    
    if not game or not sender or not receiver:
        return jsonify({'message': 'Game or player not found'}), 404
        
    # Verify requesting user is the sender
    if sender.user_id != user_id:
        return jsonify({'message': 'Cannot create trade for another player'}), 403
        
    # Create trade
    new_trade = Trade(
        game_id=game_id,
        sender_id=sender.id,
        receiver_id=receiver.id
    )
    db.session.add(new_trade)
    db.session.flush()  # To get the trade ID
    
    # Add trade items (offer)
    for item in data['offer']:
        trade_item = TradeItem(
            trade_id=new_trade.id,
            type=item['type'],
            property_id=item.get('property_id'),
            amount=item.get('amount'),
            from_sender=True
        )
        db.session.add(trade_item)
    
    # Add trade items (request)
    for item in data['request']:
        trade_item = TradeItem(
            trade_id=new_trade.id,
            type=item['type'],
            property_id=item.get('property_id'),
            amount=item.get('amount'),
            from_sender=False
        )
        db.session.add(trade_item)
    
    db.session.commit()
    
    record_game_history(game_id, sender.id, 'trade_created', f'with player {receiver.id}')
    return jsonify({'message': 'Trade created', 'trade_id': new_trade.id}), 201

@app.route('/games/<int:game_id>/trade/<int:trade_id>/accept', methods=['POST'])
@jwt_required()
def accept_trade(game_id, trade_id):
    """
    Accept a trade offer.
    ---
    tags:
      - Trade
    parameters:
      - in: path
        name: game_id
        required: true
        type: integer
      - in: path
        name: trade_id
        required: true
        type: integer
    responses:
      200:
        description: Trade accepted
        schema:
          type: object
          properties:
            message:
              type: string
      404:
        description: Trade not found
      400:
        description: Cannot accept trade
    """
    user_id = get_jwt_identity()
    trade = Trade.query.filter_by(id=trade_id, game_id=game_id).first()
    
    if not trade:
        return jsonify({'message': 'Trade not found'}), 404
        
    # Verify requesting user is the receiver
    if trade.receiver.user_id != user_id:
        return jsonify({'message': 'Cannot accept this trade'}), 403
        
    if trade.status != 'pending':
        return jsonify({'message': 'Trade already processed'}), 400
        
    # Get all trade items
    trade_items = TradeItem.query.filter_by(trade_id=trade.id).all()
    
    # Verify trade is still valid (players still own properties, have enough money, etc.)
    for item in trade_items:
        if item.type == 'property' and item.from_sender:
            if item.property.owner_id != trade.sender_id:
                return jsonify({'message': 'Sender no longer owns offered property'}), 400
        elif item.type == 'money' and item.from_sender:
            if trade.sender.balance < item.amount:
                return jsonify({'message': 'Sender no longer has enough money'}), 400
        elif item.type == 'get_out_of_jail_card' and item.from_sender:
            if trade.sender.get_out_of_jail_cards < 1:
                return jsonify({'message': 'Sender no longer has get out of jail card'}), 400
                
        # Similar checks for receiver's items
        if item.type == 'property' and not item.from_sender:
            if item.property.owner_id != trade.receiver_id:
                return jsonify({'message': 'Receiver no longer owns requested property'}), 400
        elif item.type == 'money' and not item.from_sender:
            if trade.receiver.balance < item.amount:
                return jsonify({'message': 'Receiver no longer has enough money'}), 400
        elif item.type == 'get_out_of_jail_card' and not item.from_sender:
            if trade.receiver.get_out_of_jail_cards < 1:
                return jsonify({'message': 'Receiver no longer has get out of jail card'}), 400
    
    # Execute the trade
    for item in trade_items:
        if item.type == 'property':
            if item.from_sender:
                item.property.owner_id = trade.receiver_id
            else:
                item.property.owner_id = trade.sender_id
        elif item.type == 'money':
            if item.from_sender:
                trade.sender.balance -= item.amount
                trade.receiver.balance += item.amount
            else:
                trade.receiver.balance -= item.amount
                trade.sender.balance += item.amount
        elif item.type == 'get_out_of_jail_card':
            if item.from_sender:
                trade.sender.get_out_of_jail_cards -= 1
                trade.receiver.get_out_of_jail_cards += 1
            else:
                trade.receiver.get_out_of_jail_cards -= 1
                trade.sender.get_out_of_jail_cards += 1
    
    trade.status = 'accepted'
    db.session.commit()
    
    record_game_history(game_id, trade.receiver_id, 'trade_accepted', f'trade {trade.id}')
    return jsonify({'message': 'Trade accepted'}), 200

@app.route('/games/<int:game_id>/trade/<int:trade_id>/reject', methods=['POST'])
@jwt_required()
def reject_trade(game_id, trade_id):
    """
    Reject a trade offer.
    ---
    tags:
      - Trade
    parameters:
      - in: path
        name: game_id
        required: true
        type: integer
      - in: path
        name: trade_id
        required: true
        type: integer
    responses:
      200:
        description: Trade rejected
        schema: 
          type: object
          properties:
            message:
              type: string
      404:
        description: Trade not found
      400:
        description: Cannot reject trade
    """
    user_id = get_jwt_identity()
    trade = Trade.query.filter_by(id=trade_id, game_id=game_id).first()
    
    if not trade:
        return jsonify({'message': 'Trade not found'}), 404
        
    # Verify requesting user is the receiver
    if trade.receiver.user_id != user_id:
        return jsonify({'message': 'Cannot reject this trade'}), 403
        
    if trade.status != 'pending':
        return jsonify({'message': 'Trade already processed'}), 400
        
    trade.status = 'rejected'
    db.session.commit()
    
    record_game_history(game_id, trade.receiver_id, 'trade_rejected', f'trade {trade.id}')
    return jsonify({'message': 'Trade rejected'}), 200

### Auction Endpoints ###
@app.route('/games/<int:game_id>/auction', methods=['POST'])
@jwt_required()
def start_auction(game_id):
    """
    Start an auction for a property.
    ---
    tags:
      - Auction
    parameters:
      - in: path
        name: game_id
        required: true
        type: integer
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            property_id:
              type: integer
            starting_bid:
              type: integer
    responses:
      201:
        description: Auction started
        schema:
          type: object
          properties:
            message:
              type: string
            auction_id:
              type: integer
      404:
        description: Game or property not found
      400:
        description: Property already owned
    """
    property = Property.query.filter_by(id=request.json['property_id'], game_id=game_id).first()
    if not property:
        return jsonify({'message': 'Property not found'}), 404
        
    if property.owner_id:
        return jsonify({'message': 'Property already owned'}), 400
        
    new_auction = Auction(
        game_id=game_id,
        property_id=property.id,
        current_bid=request.json.get('starting_bid', property.price // 2),
        status='active'
    )
    db.session.add(new_auction)
    db.session.commit()
    
    record_game_history(game_id, None, 'auction_started', f'for property {property.id}')
    return jsonify({'message': 'Auction started', 'auction_id': new_auction.id}), 201

@app.route('/games/<int:game_id>/auction/<int:auction_id>/bid', methods=['POST'])
@jwt_required()
def place_bid(game_id, auction_id):
    """
    Place a bid in an auction.
    ---
    tags:
      - Auction
    parameters:
      - in: path
        name: game_id
        required: true
        type: integer
      - in: path
        name: auction_id
        required: true
        type: integer
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            player_id:
              type: integer
            amount:
              type: integer
    responses:
      200:
        description: Bid placed
        schema:
          type: object
          properties:
            message:
              type: string
      404:
        description: Auction or player not found
      400:
        description: Invalid bid
    """
    user_id = get_jwt_identity()
    auction = Auction.query.filter_by(id=auction_id, game_id=game_id).first()
    player = Player.query.filter_by(id=request.json['player_id'], game_id=game_id).first()
    
    if not auction or not player:
        return jsonify({'message': 'Auction or player not found'}), 404
        
    if player.user_id != user_id:
        return jsonify({'message': 'Cannot bid for another player'}), 403
        
    if auction.status != 'active':
        return jsonify({'message': 'Auction not active'}), 400
        
    if request.json['amount'] <= auction.current_bid:
        return jsonify({'message': 'Bid must be higher than current bid'}), 400
        
    if player.balance < request.json['amount']:
        return jsonify({'message': 'Insufficient funds'}), 400
        
    auction.current_bid = request.json['amount']
    auction.current_bidder_id = player.id
    db.session.commit()
    
    record_game_history(game_id, player.id, 'auction_bid', f'amount {request.json["amount"]}')
    return jsonify({'message': 'Bid placed'}), 200

@app.route('/games/<int:game_id>/auction/<int:auction_id>/end', methods=['POST'])
@jwt_required()
def end_auction(game_id, auction_id):
    """
    End an auction.
    ---
    tags:
      - Auction
    parameters:
      - in: path
        name: game_id
        required: true
        type: integer
      - in: path
        name: auction_id
        required: true
        type: integer
    responses:
      200:
        description: Auction ended
        schema:
          type: object
          properties:
            message:
              type: string
            winner_id:
              type: integer
            property_id:
              type: integer
            amount:
              type: integer
      404:
        description: Auction not found
      400:
        description: Cannot end auction
    """
    auction = Auction.query.filter_by(id=auction_id, game_id=game_id).first()
    if not auction:
        return jsonify({'message': 'Auction not found'}), 404
        
    if auction.status != 'active':
        return jsonify({'message': 'Auction already ended'}), 400
        
    if not auction.current_bidder_id:
        # No bids were placed
        auction.status = 'completed'
        db.session.commit()
        return jsonify({'message': 'Auction ended with no winner'}), 200
    
    # Transfer property to highest bidder
    property = Property.query.get(auction.property_id)
    player = Player.query.get(auction.current_bidder_id)
    
    if player.balance < auction.current_bid:
        return jsonify({'message': 'Bidder cannot afford the bid'}), 400
        
    player.balance -= auction.current_bid
    property.owner_id = player.id
    auction.status = 'completed'
    db.session.commit()
    
    record_game_history(game_id, player.id, 'auction_won', 
                       f'property {property.name} for ${auction.current_bid}')
    return jsonify({
        'message': 'Auction ended',
        'winner_id': player.id,
        'property_id': property.id,
        'amount': auction.current_bid
    }), 200

### Card Endpoints ###
@app.route('/games/<int:game_id>/card/draw', methods=['POST'])
@jwt_required()
def draw_card(game_id):
    """
    Draw a chance or community chest card.
    ---
    tags:
      - Card
    parameters:
      - in: path
        name: game_id
        required: true
        type: integer
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            player_id:
              type: integer
            card_type:
              type: string
              enum: [chance, community_chest]
    responses:
      200:
        description: Card drawn
        schema:
          type: object
          properties:
            message:
              type: string
            card:
              type: object
              properties:
                title:
                  type: string
                description:
                  type: string
                action:
                  type: string
                amount:
                  type: integer
                position:
                  type: integer
      404:
        description: Game or player not found
    """
    user_id = get_jwt_identity()
    data = request.get_json()
    player = Player.query.filter_by(id=data['player_id'], game_id=game_id).first()
    
    if not player:
        return jsonify({'message': 'Player not found'}), 404
        
    if player.user_id != user_id:
        return jsonify({'message': 'Cannot draw card for another player'}), 403
        
    # Get a random card of the requested type
    card = Card.query.filter_by(game_id=game_id, type=data['card_type']).order_by(db.func.random()).first()
    
    if not card:
        return jsonify({'message': 'No cards of this type available'}), 400
        
    # Process card action
    message = f"Drew card: {card.title}"
    if card.action == 'move':
        player.position = card.position
        message += f". Moved to position {card.position}"
    elif card.action == 'pay':
        player.balance -= card.amount
        message += f". Paid ${card.amount}"
    elif card.action == 'receive':
        player.balance += card.amount
        message += f". Received ${card.amount}"
    elif card.action == 'jail':
        player.in_jail = True
        player.position = 10  # Jail position
        message += ". Sent to jail"
    elif card.action == 'get_out_of_jail':
        player.get_out_of_jail_cards += 1
        message += ". Received Get Out of Jail Free card"
    
    db.session.commit()
    record_game_history(game_id, player.id, 'card_drawn', card.title)
    
    return jsonify({
        'message': message,
        'card': {
            'title': card.title,
            'description': card.description,
            'action': card.action,
            'amount': card.amount,
            'position': card.position
        }
    }), 200

### Jail Endpoints ###
@app.route('/games/<int:game_id>/jail/pay', methods=['POST'])
@jwt_required()
def pay_jail_fine(game_id):
    """
    Pay to get out of jail.
    ---
    tags:
      - Jail
    parameters:
      - in: path
        name: game_id
        required: true
        type: integer
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            player_id:
              type: integer
    responses:
      200:
        description: Paid jail fine
        schema:
          type: object
          properties:
            message:
              type: string
      404:
        description: Player not found
      400:
        description: Cannot pay jail fine
    """
    user_id = get_jwt_identity()
    player = Player.query.filter_by(id=request.json['player_id'], game_id=game_id).first()
    
    if not player:
        return jsonify({'message': 'Player not found'}), 404
        
    if player.user_id != user_id:
        return jsonify({'message': 'Cannot pay for another player'}), 403
        
    if not player.in_jail:
        return jsonify({'message': 'Not in jail'}), 400
        
    if player.balance < 50:
        return jsonify({'message': 'Insufficient funds'}), 400
        
    player.in_jail = False
    player.jail_turns = 0
    player.balance -= 50
    db.session.commit()
    
    record_game_history(game_id, player.id, 'paid_jail_fine')
    return jsonify({'message': 'Paid $50 to get out of jail'}), 200

@app.route('/games/<int:game_id>/jail/use_card', methods=['POST'])
@jwt_required()
def use_jail_card(game_id):
    """
    Use Get Out of Jail Free card.
    ---
    tags:
      - Jail
    parameters:
      - in: path
        name: game_id
        required: true
        type: integer
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            player_id:
              type: integer
    responses:
      200:
        description: Used jail card
        schema:
          type: object
          properties:
            message:
              type: string
      404:
        description: Player not found
      400:
        description: Cannot use jail card
    """
    user_id = get_jwt_identity()
    player = Player.query.filter_by(id=request.json['player_id'], game_id=game_id).first()
    
    if not player:
        return jsonify({'message': 'Player not found'}), 404
        
    if player.user_id != user_id:
        return jsonify({'message': 'Cannot use card for another player'}), 403
        
    if not player.in_jail:
        return jsonify({'message': 'Not in jail'}), 400
        
    if player.get_out_of_jail_cards < 1:
        return jsonify({'message': 'No Get Out of Jail Free cards'}), 400
        
    player.in_jail = False
    player.jail_turns = 0
    player.get_out_of_jail_cards -= 1
    db.session.commit()
    
    record_game_history(game_id, player.id, 'used_jail_card')
    return jsonify({'message': 'Used Get Out of Jail Free card'}), 200

### Bankruptcy Endpoints ###
@app.route('/games/<int:game_id>/player/<int:player_id>/bankrupt', methods=['POST'])
@jwt_required()
def declare_bankruptcy(game_id, player_id):
    """
    Declare bankruptcy.
    ---
    tags:
      - Bankruptcy
    parameters:
      - in: path
        name: game_id
        required: true
        type: integer
      - in: path
        name: player_id
        required: true
        type: integer
    responses:
      200:
        description: Bankruptcy declared
        schema:
          type: object
          properties:
            message:
              type: string
      404:
        description: Player not found
      400:
        description: Cannot declare bankruptcy
    """
    user_id = get_jwt_identity()
    player = Player.query.filter_by(id=player_id, game_id=game_id).first()
    
    if not player:
        return jsonify({'message': 'Player not found'}), 404
        
    if player.user_id != user_id:
        return jsonify({'message': 'Cannot declare bankruptcy for another player'}), 403
        
    if player.is_bankrupt:
        return jsonify({'message': 'Already bankrupt'}), 400
        
    # Transfer all properties to bank (owner_id = None)
    Property.query.filter_by(owner_id=player.id).update({'owner_id': None})
    
    # Mark player as bankrupt
    player.is_bankrupt = True
    db.session.commit()
    
    # Check if game should end (only one player left)
    active_players = Player.query.filter_by(game_id=game_id, is_bankrupt=False).count()
    if active_players <= 1:
        end_game(game_id)
        return jsonify({'message': 'Bankruptcy declared - game over'}), 200
    
    record_game_history(game_id, player.id, 'declared_bankruptcy')
    return jsonify({'message': 'Bankruptcy declared'}), 200

### Game Endpoints ###
@app.route('/games/<int:game_id>/end', methods=['POST'])
@jwt_required()
def end_game(game_id):
    """
    End a game.
    ---
    tags:
      - Game
    parameters:
      - in: path
        name: game_id
        required: true
        type: integer
    responses:
      200:
        description: Game ended
        schema:
          type: object
          properties:
            message:
              type: string
            winner_id:
              type: integer
      404:
        description: Game not found
    """
    game = Game.query.get(game_id)
    if not game:
        return jsonify({'message': 'Game not found'}), 404
        
    game.status = 'finished'
    
    # Determine winner (player with highest net worth)
    winner = None
    max_balance = -1
    
    for player in Player.query.filter_by(game_id=game_id, is_bankrupt=False).all():
        # Calculate net worth (balance + property values)
        net_worth = player.balance
        properties = Property.query.filter_by(owner_id=player.id).all()
        for prop in properties:
            net_worth += prop.price  # Simplified valuation
            
        if net_worth > max_balance:
            max_balance = net_worth
            winner = player
    
    if winner:
        user = User.query.get(winner.user_id)
        user.games_played += 1
        user.games_won += 1
        db.session.commit()
    
    record_game_history(game_id, winner.id if winner else None, 'game_ended')
    return jsonify({
        'message': 'Game ended',
        'winner_id': winner.id if winner else None
    }), 200

@app.route('/games/<int:game_id>/history', methods=['GET'])
@jwt_required()
def get_game_history(game_id):
    """
    Get game history.
    ---
    tags:
      - Game
    parameters:
      - in: path
        name: game_id
        required: true
        type: integer
    responses:
      200:
        description: Game history
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
              player_id:
                type: integer
              action:
                type: string
              details:
                type: string
              timestamp:
                type: string
      404:
        description: Game not found
    """
    game = Game.query.get(game_id)
    if not game:
        return jsonify({'message': 'Game not found'}), 404
        
    history = GameHistory.query.filter_by(game_id=game_id).order_by(GameHistory.created_at).all()
    
    return jsonify([{
        'id': h.id,
        'player_id': h.player_id,
        'action': h.action,
        'details': h.details,
        'timestamp': h.created_at.isoformat()
    } for h in history]), 200


# Get all games history of a player
@app.route('/users/<int:user_id>/history', methods=['GET'])
@jwt_required()
def get_user_history(user_id):
  """
  Get all games history of a user.
  ---
  tags:
    - Users
  parameters:
    - in: path
      name: user_id
      required: true
      type: integer
  responses:
    200:
      description: User history
      schema:
        type: array
        items:
          type: object
          properties:
            id:
              type: integer
            game_id:
              type: integer
            action:
              type: string
            details:
              type: string
            timestamp:
              type: string
    404:
      description: User not found
  """
  user = User.query.get(user_id)
  if not user:
    return jsonify({'message': 'User not found'}), 404

  # Fetch all games the user participated in
  player_games = Player.query.filter_by(user_id=user_id).all()

  # Prepare the response with games won and placements
  games_summary = []
  for player in player_games:
    game = Game.query.get(player.game_id)
    if not game:
      continue

    # Determine placement by comparing net worth of all players in the game
    players = Player.query.filter_by(game_id=player.game_id).all()
    net_worths = [
      (p.id, p.balance + sum(prop.price for prop in Property.query.filter_by(owner_id=p.id).all()))
      for p in players
    ]
    net_worths.sort(key=lambda x: x[1], reverse=True)
    placement = next((i + 1 for i, (pid, _) in enumerate(net_worths) if pid == player.id), None)

    games_summary.append({
      'game_id': player.game_id,
      'placement': placement,
      'won': placement == 1
    })

  return jsonify(games_summary), 200
    

@app.route('/users', methods=['GET'])
def get_users():
    """
    Get all users.
    ---
    tags:
      - Users
    responses:
      200:
        description: List of users
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
              username:
                type: string
              games_played:
                type: integer
              games_won:
                type: integer
      404:
        description: No users found
      400:
        description: Invalid request
    """
    users = User.query.all()
    return jsonify([{
        'id': user.id,
        'username': user.username,
        'games_played': user.games_played,
        'games_won': user.games_won
    } for user in users]), 200  



if __name__ == '__main__':
    app.run(debug=True)