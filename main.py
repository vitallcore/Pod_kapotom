from fastapi import FastAPI #Импорт FastAPI

app = FastAPI() #Создание экземпляра точки входа 


@app.get("/") #Декоратор запроса
async def root(): #Функция для выполнения по пути указаноому выше
    return {"message": "Hello World"} #Возвращение результата при переходе по пути декоратора 
