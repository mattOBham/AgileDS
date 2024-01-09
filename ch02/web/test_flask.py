from flask import Flask, request


app = Flask(__name__)


@app.route("/<input>")
def hello(input):
    return input


if __name__ == "__main__":
    app.run(debug=True, host='localhost')
