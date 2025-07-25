from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import base64
import httpx
import json
from typing import List, Dict, Any

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = "AIzaSyBqL4M8InLUCiW-fqaCvgQ9JItPm87OdwI"
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

@app.get("/")
async def root():
    return {"message": "Сервер запущен и готов!"}

@app.post("/analyze-fridge/")
async def analyze_fridge(
    file: UploadFile = File(...),
    selected_allergens: str = Form("[]")
):
    products = []
    nutrition = []
    recipes = []

    try:
        image_bytes = await file.read()
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        allergens_list = json.loads(selected_allergens)
        print(f"Приняты аллергены: {allergens_list}")

        try:
            products_query = (
                "Найди все продукты на фото. Для каждого продукта дай русское название, "
                "аллергены (используй только: 'глютен', 'молоко', 'яйца', 'орехи', 'морепродукты', 'соя', 'арахис', 'рыба', 'сельдерей', 'горчица', 'кунжут', 'сульфиты'), "
                "и категорию (например, 'молочные продукты', 'овощи'). "
                "Ответь в формате JSON: массив объектов с полями `name`, `allergens` (массив строк), `category`."
            )
            products_data = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": products_query},
                            {"inlineData": {"mimeType": file.content_type, "data": base64_image}}
                        ]
                    }
                ],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "name": {"type": "STRING"},
                                "allergens": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "category": {"type": "STRING"}
                            },
                            "propertyOrdering": ["name", "allergens", "category"]
                        }
                    }
                }
            }

            async with httpx.AsyncClient(timeout=90.0) as client:
                products_response = await client.post(
                    f"{API_URL}?key={API_KEY}",
                    json=products_data
                )
                products_response.raise_for_status()
                products_result = products_response.json()

            if products_result.get("candidates") and products_result["candidates"][0].get("content"):
                try:
                    json_text = products_result["candidates"][0]["content"]["parts"][0]["text"]
                    products = json.loads(json_text)
                    print(f"Распознаны продукты: {products}")
                except json.JSONDecodeError:
                    print(f"Ошибка чтения JSON для продуктов: {json_text}")
                    products = []
            else:
                print(f"Gemini не вернул продукты: {products_result}")

        except httpx.HTTPStatusError as e:
            print(f"HTTP ошибка от Gemini (продукты): {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            print(f"Сетевая ошибка при запросе продуктов: {e}")
        except Exception as e:
            print(f"Неизвестная ошибка при поиске продуктов: {e}")

        if not products:
            return JSONResponse(status_code=200, content={
                "products": [],
                "nutrition_info": [],
                "recipes": [],
                "message": "Продукты не найдены."
            })

        available_products_text = ", ".join([
            f"{p['name']} (аллергены: {', '.join(p['allergens']) or 'нет'})"
            for p in products
        ])

        try:
            nutrition_query = (
                f"На основе этих продуктов: {available_products_text}, "
                "дай примерную пищевую ценность для сбалансированного рациона. "
                "Покажи белки, углеводы, жиры, клетчатку, витамин C, кальций "
                "и их процент от нормы. Ответь в JSON: массив объектов с полями `label`, `value`, `percentage`."
            )
            nutrition_data = {
                "contents": [{"role": "user", "parts": [{"text": nutrition_query}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "label": {"type": "STRING"},
                                "value": {"type": "STRING"},
                                "percentage": {"type": "NUMBER"}
                            },
                            "propertyOrdering": ["label", "value", "percentage"]
                        }
                    }
                }
            }

            async with httpx.AsyncClient(timeout=90.0) as client:
                nutrition_response = await client.post(
                    f"{API_URL}?key={API_KEY}",
                    json=nutrition_data
                )
                nutrition_response.raise_for_status()
                nutrition_result = nutrition_response.json()

            if nutrition_result.get("candidates") and nutrition_result["candidates"][0].get("content"):
                json_text = nutrition_result["candidates"][0]["content"]["parts"][0]["text"]
                nutrition = json.loads(json_text)
        except (httpx.HTTPStatusError, json.JSONDecodeError) as e:
            print(f"Ошибка при получении питания: {e}")
        except httpx.RequestError as e:
            print(f"Сетевая ошибка при запросе питания: {e}")
        except Exception as e:
            print(f"Неизвестная ошибка при получении питания: {e}")

        try:
            allergens_text = ", ".join(allergens_list) if allergens_list else "нет"
            recipe_query = (
                f"Используя эти продукты: {available_products_text}, "
                f"и избегая аллергенов: {allergens_text}, "
                "создай план питания на день (Завтрак, Обед, Ужин, Перекус). "
                "Для каждого приема пищи дай рецепт, время готовки (мин), порции, "
                "калории и список ингредиентов. "
                "Ответь в JSON: массив объектов с полями `title`, `mealType`, `cookTime`, `servings`, `calories`, `ingredients` (массив строк), "
                "`description`, `requiredProducts` (массив строк), `allergens` (массив строк)."
            )
            recipe_data = {
                "contents": [{"role": "user", "parts": [{"text": recipe_query}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "title": {"type": "STRING"},
                                "mealType": {"type": "STRING"},
                                "cookTime": {"type": "NUMBER"},
                                "servings": {"type": "NUMBER"},
                                "calories": {"type": "NUMBER"},
                                "ingredients": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "description": {"type": "STRING"},
                                "requiredProducts": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "allergens": {"type": "ARRAY", "items": {"type": "STRING"}}
                            },
                            "propertyOrdering": ["title", "mealType", "cookTime", "servings", "calories", "ingredients", "description", "requiredProducts", "allergens"]
                        }
                    }
                }
            }

            async with httpx.AsyncClient(timeout=150.0) as client:
                recipe_response = await client.post(
                    f"{API_URL}?key={API_KEY}",
                    json=recipe_data
                )
                recipe_response.raise_for_status()
                recipe_result = recipe_response.json()

            if recipe_result.get("candidates") and recipe_result["candidates"][0].get("content"):
                json_text = recipe_result["candidates"][0]["content"]["parts"][0]["text"]
                recipes = json.loads(json_text)
        except (httpx.HTTPStatusError, json.JSONDecodeError) as e:
            print(f"Ошибка при получении рецептов: {e}")
        except httpx.RequestError as e:
            print(f"Сетевая ошибка при запросе рецептов: {e}")
        except Exception as e:
            print(f"Неизвестная ошибка при получении рецептов: {e}")

        return JSONResponse(content={
            "products": products,
            "nutrition_info": nutrition,
            "recipes": recipes
        })

    except Exception as e:
        print(f"Общая ошибка на сервере: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")
