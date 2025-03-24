# Monopoly - The web game backend

## Setup and run:
- Install python3
- Install all the requirements using `pip install -r requirements.txt`
- Setup the backend by running the following commands:
  - Windows:
  ```bash
  set FLASK_APP=main.py
  ```  
  - Unix: 
  ```bash
  export FLASK_APP=main.py
  ```
- After running those commands, initialize the database
    ```bash
    flask --app main db init
    flask --app main db migrate -m "Initial database setup"
    flask --app main db upgrade
    ```

- Run the backend by using `python3 main.py`
- visit [the default backend documentation](http://127.0.0.1:5000/)