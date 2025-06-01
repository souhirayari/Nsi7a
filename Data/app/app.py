from flask import Flask, request, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
from pymongo.errors import ConnectionFailure

app = Flask(__name__)

# Connexion à MongoDB (local)
try:
    client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=3000)
    client.admin.command('ping')  # Vérifie si le serveur répond
    print("Connexion à MongoDB réussie.")
except ConnectionFailure:
    print("Échec de connexion à MongoDB.")
    exit()

#  Base et collection
db = client["produits"]
collection = db["produits"]

# Sérialiser un document MongoDB
def serialize_produit(produit):
    produit["_id"] = str(produit["_id"])
    return produit

# Créer un produit
@app.route('/produits', methods=['POST'])
def create_produit():
    data = request.json
    produit = {
        "productID": data["productID"],
        "productName": data["productName"],
        "description": data["description"],
        "price": float(data["price"]),
        "quantity": int(data["quantity"])
    }
    result = collection.insert_one(produit)
    return jsonify({"message": "Produit ajouté", "id": str(result.inserted_id)}), 201

# Lire tous les produits
@app.route('/produits', methods=['GET'])
def get_all_produits():
    produits = list(collection.find())
    return jsonify([serialize_produit(p) for p in produits])

# Lire un produit par ID
@app.route('/produits/<id>', methods=['GET'])
def get_produit(id):
    produit = collection.find_one({"_id": ObjectId(id)})
    if produit:
        return jsonify(serialize_produit(produit))
    return jsonify({"error": "Produit introuvable"}), 404

# Modifier un produit
@app.route('/produits/<id>', methods=['PUT'])
def update_produit(id):
    data = request.json
    update_result = collection.update_one(
        {"_id": ObjectId(id)},
        {"$set": {
            "productID": data["productID"],
            "productName": data["productName"],
            "description": data["description"],
            "price": float(data["price"]),
            "quantity": int(data["quantity"])
        }}
    )
    if update_result.modified_count:
        return jsonify({"message": "Produit mis à jour"})
    return jsonify({"error": "Aucune modification"}), 404

# Supprimer un produit
@app.route('/produits/<id>', methods=['DELETE'])
def delete_produit(id):
    result = collection.delete_one({"_id": ObjectId(id)})
    if result.deleted_count:
        return jsonify({"message": "Produit supprimé"})
    return jsonify({"error": "Produit introuvable"}), 404

# Route de test pour voir si le serveur tourne
@app.route('/')
def home():
    return jsonify({"message": "🚀 API Flask MongoDB est en ligne et connectée"})

if __name__ == '__main__':
    app.run(debug=True)
