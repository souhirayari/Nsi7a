import http.server
import socketserver
import json
import requests
import sys
import traceback
from pymongo import MongoClient
from bson import ObjectId
from urllib.parse import parse_qs, urlparse
import re
from datetime import datetime
from collections import deque

class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)

class ConversationLogger:
    _instance = None
    
    def __new__(cls, max_conversations=10):
        if cls._instance is None:
            cls._instance = super(ConversationLogger, cls).__new__(cls)
            cls._instance.client = MongoClient('mongodb://localhost:27017/')
            cls._instance.db = cls._instance.client['products']
            cls._instance.conversations = cls._instance.db['conversations']
            print(f"Initialized ConversationLogger with MongoDB collection")
        return cls._instance
    
    def add_conversation(self, user_question, ai_response):
        try:
            conversation = {
                'timestamp': datetime.now(),
                'user_question': user_question,
                'ai_response': ai_response,
                'status': 'Resolved'  # You can make this dynamic based on response content
            }
            self.conversations.insert_one(conversation)
            print(f"Added conversation to MongoDB: {conversation}")
        except Exception as e:
            print(f"Error adding conversation: {str(e)}")
            print(traceback.format_exc())
    
    def get_conversations(self):
        try:
            # Get the most recent conversations, sorted by timestamp
            conversations = list(self.conversations.find().sort('timestamp', -1))
            # Convert ObjectId to string and datetime to string for JSON serialization
            for conv in conversations:
                conv['_id'] = str(conv['_id'])
                conv['timestamp'] = conv['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            print(f"Retrieved {len(conversations)} conversations from MongoDB")
            return conversations
        except Exception as e:
            print(f"Error getting conversations: {str(e)}")
            print(traceback.format_exc())
            return []

class DatabaseHandler:
    def __init__(self):
        self.client = None
        self.db = None
        self.collection = None
        self.connect()

    def connect(self):
        try:
            print("Attempting to connect to MongoDB...")
            self.client = MongoClient('mongodb://localhost:27017/')
            self.db = self.client['products']
            self.collection = self.db['products']
            print("Connected to MongoDB successfully")
        except Exception as e:
            print(f"Error connecting to MongoDB: {str(e)}")
            print(traceback.format_exc())
            raise

    def get_collection_schema(self):
        try:
            print("Fetching collection schema...")
            # Get a sample document
            sample_doc = self.collection.find_one()
            if not sample_doc:
                # Return a default schema if no documents exist
                return {
                    "collection_name": "products",
                    "fields": ["_id", "productID", "productName", "description", "price", "quantity"],
                    "sample_document": {
                        "_id": "sample_id",
                        "productID": "SAMPLE001",
                        "productName": "Sample Product",
                        "description": "Sample description",
                        "price": 0.0,
                        "quantity": 0
                    }
                }
            
            # Convert ObjectId to string in sample document
            if '_id' in sample_doc and isinstance(sample_doc['_id'], ObjectId):
                sample_doc['_id'] = str(sample_doc['_id'])
            
            # Get all fields from the sample document
            fields = list(sample_doc.keys())
            
            schema = {
                "collection_name": "products",
                "fields": fields,
                "sample_document": sample_doc
            }
            print("Schema fetched successfully:", schema)
            return schema
        except Exception as e:
            print(f"Error getting schema: {str(e)}")
            print(traceback.format_exc())
            return {
                "collection_name": "products",
                "fields": ["_id", "productID", "productName", "description", "price", "quantity"],
                "sample_document": {
                    "_id": "sample_id",
                    "productID": "SAMPLE001",
                    "productName": "Sample Product",
                    "description": "Sample description",
                    "price": 0.0,
                    "quantity": 0
                }
            }

    def find_products(self, query):
        try:
            print(f"Executing query: {query}")
            # Convert the query to a MongoDB query
            if isinstance(query, str):
                # If it's a string, try to parse it as JSON
                try:
                    query = json.loads(query)
                except:
                    # If not valid JSON, create a text search query
                    query = {"$text": {"$search": query}}
            
            # Execute the query
            results = list(self.collection.find(query))
            # Convert ObjectIds to strings
            for result in results:
                if '_id' in result and isinstance(result['_id'], ObjectId):
                    result['_id'] = str(result['_id'])
            print(f"Found {len(results)} results")
            return results
        except Exception as e:
            print(f"Error executing query: {str(e)}")
            print(traceback.format_exc())
            return []

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.db_handler = DatabaseHandler()
        self.conversation_logger = ConversationLogger()
        super().__init__(*args, **kwargs)

    def do_GET(self):
        try:
            print(f"Received GET request for path: {self.path}")
            
            if self.path == '/api/schema':
                schema = self.db_handler.get_collection_schema()
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                response = json.dumps(schema, cls=MongoJSONEncoder)
                print("Sending schema response:", response)
                self.wfile.write(response.encode())
                return
            
            if self.path == '/api/conversations':
                conversations = self.conversation_logger.get_conversations()
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(conversations).encode())
                return
            
            # Serve static files
            return http.server.SimpleHTTPRequestHandler.do_GET(self)
            
        except Exception as e:
            print(f"Error in GET handler: {str(e)}")
            print(traceback.format_exc())
            self.send_error(500, str(e))

    def do_POST(self):
        try:
            print(f"Received POST request for path: {self.path}")
            
            if self.path == '/api/query':
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                query_data = json.loads(post_data.decode('utf-8'))
                print("Received query data:", query_data)
                
                # Get the user's question
                user_question = query_data.get('prompt', '')
                
                # First, get the schema to understand the database structure
                schema = self.db_handler.get_collection_schema()
                print("Got schema:", schema)
                
                # Create a prompt for Ollama to extract query parameters
                extraction_prompt = f"""Given this database schema:
Collection: {schema['collection_name']}
Fields: {', '.join(schema['fields'])}

And this user question: "{user_question}"

First, understand what the user is asking for. Then, create a MongoDB query that will help answer their question.
For example:
- For "products between $50 and $100" -> {{"price": {{"$gte": 50, "$lte": 100}}}}
- For "electronics with low stock" -> {{"category": "Electronics", "quantity": {{"$lt": 10}}}}
- For "any good product recommendation" -> {{"$or": [{{"price": {{"$lt": 50}}}}, {{"quantity": {{"$gt": 10}}}}]}}

Return ONLY the JSON object, nothing else. Make sure to use double quotes for all property names."""

                # Get query parameters from Ollama
                print("Sending request to Ollama for query extraction...")
                ollama_response = requests.post('http://localhost:11434/api/generate',
                    json={
                        "model": "mistral",
                        "prompt": extraction_prompt,
                        "stream": False
                    }
                )
                print("Received response from Ollama for query extraction")
                
                if ollama_response.status_code != 200:
                    raise Exception(f"Ollama API error: {ollama_response.text}")
                
                # Extract the JSON from Ollama's response
                response_text = ollama_response.json()['response']
                # Clean up the response text to ensure it's valid JSON
                response_text = response_text.strip()
                # Remove any markdown code block markers
                response_text = re.sub(r'```json|```javascript|```', '', response_text)
                # Find the first JSON object in the text
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if not json_match:
                    raise Exception("Could not extract query parameters from AI response")
                
                try:
                    query_params = json.loads(json_match.group())
                except json.JSONDecodeError as e:
                    print(f"Error parsing JSON: {e}")
                    print(f"Raw JSON text: {json_match.group()}")
                    # If we can't parse the JSON, use a default query for recommendations
                    query_params = {"$or": [{"price": {"$lt": 50}}, {"quantity": {"$gt": 10}}]}
                
                print("Extracted query parameters:", query_params)
                
                # Execute the query
                results = self.db_handler.find_products(query_params)
                
                # Create a prompt for Ollama to interpret the results
                interpretation_prompt = f"""Given these database results:
{json.dumps(results, cls=MongoJSONEncoder, indent=2)}

And the original user question: "{user_question}"

Create a friendly, conversational response that:
1. Acknowledges the user's question
2. Summarizes the findings
3. Highlights key information about the products
4. Makes recommendations if appropriate
5. Uses emojis to make the response more engaging

Keep the response concise but informative."""

                # Get interpretation from Ollama
                print("Sending request to Ollama for response interpretation...")
                interpretation_response = requests.post('http://localhost:11434/api/generate',
                    json={
                        "model": "mistral",
                        "prompt": interpretation_prompt,
                        "stream": False
                    }
                )
                
                if interpretation_response.status_code != 200:
                    raise Exception(f"Ollama API error: {interpretation_response.text}")
                
                # Get the interpreted response
                response = interpretation_response.json()['response'].strip()
                
                # Log the conversation
                self.conversation_logger.add_conversation(user_question, response)
                
                # Send the response
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"response": response}).encode())
                return
                
        except Exception as e:
            print(f"Error in POST handler: {str(e)}")
            print(traceback.format_exc())
            self.send_error(500, str(e))

def run_server(port=8000):
    handler = CustomHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"Server running on port {port}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            httpd.server_close()

if __name__ == "__main__":
    run_server() 