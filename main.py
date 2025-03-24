from flask import Flask, request, jsonify, redirect
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from models import db, User, Game, Player, Property
from flasgger import Swagger

app = Flask(__name__)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///monopoly.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = 'verysecretkey'

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)
jwt = JWTManager(app)
swagger = Swagger(app)

# redirect default route to /apidocs
@app.route('/')
def index():
    return redirect('/apidocs')

@app.route('/users')
def get_users():
    """
    Get all users.
    ---
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
              pass:
                type: string
    """
    users = User.query.all()
    user_list = [{'id': user.id, 'username': user.username, 'pass': user.password} for user in users]
    return jsonify(user_list)


# Routes
@app.route('/register', methods=['POST'])
def register():
    """
    Register a new user.
    ---
    parameters:
      - in: body
        name: user
        description: The user to register
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
      400:
        description: Username already exists
    """
    data = request.get_json()
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'message': 'Username already exists'}), 400

    new_user = User(username=data['username'], password=data['password'])
    db.session.add(new_user)
    db.session.commit()
    
    return jsonify({'message': 'User registered successfully'}), 201

@app.route('/login', methods=['POST'])
def login():
    """
    Authenticate a user.
    ---
    parameters:
      - in: body
        name: user
        description: The user to authenticate
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

    access_token = create_access_token(identity=user.id)
    return jsonify({'token': access_token}), 200

@app.route('/start_game', methods=['POST'])
#@jwt_required()
def start_game():
    """
    Start a new game of Monopoly.
    ---
    responses:
      201:
        description: Game started
        schema:
          type: object
          properties:
            message:
              type: string
            game_id:
              type: integer
    """
    new_game = Game(status='active')
    db.session.add(new_game)
    db.session.commit()
    
    return jsonify({'message': 'Game started', 'game_id': new_game.id}), 201

@app.route('/join_game', methods=['POST'])
#@jwt_required()
def join_game():
    """
    Join an existing game.
    ---
    parameters:
      - in: body
        name: game
        description: The game details to join
        required: true
        schema:
          type: object
          properties:
            game_id:
              type: integer
            user_id:
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
    """
    data = request.get_json()
    game = Game.query.get(data['game_id'])
    
    if not game:
        return jsonify({'message': 'Game not found'}), 404

    new_player = Player(user_id=data['user_id'], game_id=game.id)
    db.session.add(new_player)
    db.session.commit()
    
    return jsonify({'message': 'Player joined', 'player_id': new_player.id}), 200

@app.route('/roll_dice', methods=['POST'])
#@jwt_required()
def roll_dice():
    """
    Roll dice and move player.
    ---
    parameters:
      - in: body
        name: game
        description: The game details to roll dice
        required: true
        schema:
          type: object
          properties:
            game_id:
              type: integer
            player_id:
              type: integer
    responses:
      200:
        description: Dice rolled and player moved
        schema:
          type: object
          properties:
            message:
              type: string
            dice_result:
              type: integer
            new_position:
              type: integer
      404:
        description: Game or player not found
    """
    data = request.get_json()
    game = Game.query.get(data['game_id'])
    player = Player.query.get(data['player_id'])
    
    if not game or not player:
        return jsonify({'message': 'Game or player not found'}), 404

    # simulare dat cu zaru
    import random
    dice_result = random.randint(1, 6)
    new_position = (player.position + dice_result) % 40  # 40 positions on the board
    
    player.position = new_position
    db.session.commit()
    
    return jsonify({'message': 'Dice rolled and player moved', 'dice_result': dice_result, 'new_position': new_position}), 200

@app.route('/buy_property', methods=['POST'])
#@jwt_required()
def buy_property():
    """
    Buy a property on the board.
    ---
    parameters:
      - in: body
        name: game
        description: The game details to buy property
        required: true
        schema:
          type: object
          properties:
            game_id:
              type: integer
            player_id:
              type: integer
            property_id:
              type: integer
    responses:
      200:
        description: Property purchased
        schema:
          type: object
          properties:
            message:
              type: string
      404:
        description: Game, player, or property not found
      400:
        description: Property already owned or insufficient funds
    """
    data = request.get_json()
    game = Game.query.get(data['game_id'])
    player = Player.query.get(data['player_id'])
    property = Property.query.get(data['property_id'])
    
    if not game or not player or not property:
        return jsonify({'message': 'Game, player, or property not found'}), 404

    if property.owner_id:
        return jsonify({'message': 'Property already owned'}), 400

    # Simulate property purchase
    property.owner_id = player.id
    db.session.commit()
    
    return jsonify({'message': 'Property purchased'}), 200

@app.route('/pay_rent', methods=['POST'])
#@jwt_required()
def pay_rent():
    """
    Pay rent to a property owner.
    ---
    parameters:
      - in: body
        name: game
        description: The game details to pay rent
        required: true
        schema:
          type: object
          properties:
            game_id:
              type: integer
            player_id:
              type: integer
            property_id:
              type: integer
            owner_id:
              type: integer
    responses:
      200:
        description: Rent paid
        schema:
          type: object
          properties:
            message:
              type: string
      404:
        description: Game, player, or property not found
      400:
        description: Insufficient funds
    """
    data = request.get_json()
    game = Game.query.get(data['game_id'])
    player = Player.query.get(data['player_id'])
    property = Property.query.get(data['property_id'])
    owner = Player.query.get(data['owner_id'])
    
    if not game or not player or not property or not owner:
        return jsonify({'message': 'Game, player, property, or owner not found'}), 404

    # plata chirie
    rent_amount = 50  # amount predefinit TODO: make properties different prices
    if player.balance < rent_amount:
        return jsonify({'message': 'Insufficient funds'}), 400

    player.balance -= rent_amount
    owner.balance += rent_amount
    db.session.commit()
    
    return jsonify({'message': 'Rent paid'}), 200

@app.route('/check_winner', methods=['GET'])
#@jwt_required()
def check_winner():
    """
    Check if there is a winner.
    ---
    parameters:
      - in: query
        name: game_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Winner checked
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
    game_id = request.args.get('game_id')
    game = Game.query.get(game_id)
    
    if not game:
        return jsonify({'message': 'Game not found'}), 404

    # check winner
    winner = Player.query.filter_by(game_id=game_id).order_by(Player.balance.desc()).first()
    
    return jsonify({'message': 'Winner checked', 'winner_id': winner.id}), 200

@app.route('/go_to_jail', methods=['POST'])
#@jwt_required()
def go_to_jail():
    """
    Send a player to jail.
    ---
    parameters:
      - in: body
        name: game
        description: The game details to send player to jail
        required: true
        schema:
          type: object
          properties:
            game_id:
              type: integer
            player_id:
              type: integer
    responses:
      200:
        description: Player sent to jail
        schema:
          type: object
          properties:
            message:
              type: string
      404:
        description: Game or player not found
    """
    data = request.get_json()
    game = Game.query.get(data['game_id'])
    player = Player.query.get(data['player_id'])
    
    if not game or not player:
        return jsonify({'message': 'Game or player not found'}), 404

    player.in_jail = True
    db.session.commit()
    
    return jsonify({'message': 'Player sent to jail'}), 200

@app.route('/get_out_of_jail', methods=['POST'])
#@jwt_required()
def get_out_of_jail():
    """
    Release a player from jail.
    ---
    parameters:
      - in: body
        name: game
        description: The game details to release player from jail
        required: true
        schema:
          type: object
          properties:
            game_id:
              type: integer
            player_id:
              type: integer
            method:
              type: string
              enum: [pay, roll, card]
    responses:
      200:
        description: Player released from jail
        schema:
          type: object
          properties:
            message:
              type: string
      404:
        description: Game or player not found
    """
    data = request.get_json()
    game = Game.query.get(data['game_id'])
    player = Player.query.get(data['player_id'])
    
    if not game or not player:
        return jsonify({'message': 'Game or player not found'}), 404

    player.in_jail = False
    db.session.commit()
    
    return jsonify({'message': 'Player released from jail'}), 200

# start app
if __name__ == '__main__':
    app.run(debug=True)