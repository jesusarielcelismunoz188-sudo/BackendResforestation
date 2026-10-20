from fastapi import APIRouter, HTTPException, Query, status #Crear el router http's
from Models.schemas import registroCuenca #Creacion de modelo de datos
from Services import cuencas_service #Este es el contrador

router = APIRouter(tags=["Cuencas"])

@router.get("/cuencas",status_code=status.HTTP_200_OK) #cuencas en peticion(redireccionador)
async def get_cuencas(): #Recibe la petición y envia al controlador
    """
    Retorna todas las cuencas registradas en la base de datos.
    """
    try:
        cuencas = cuencas_service.get_cuencas()
        return cuencas
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

@router.post("/cuencas", status_code=status.HTTP_201_CREATED)
async def create_cuenca(cuenca: registroCuenca):
    """
    Crea una nueva cuenca en la base de datos.
    """
    try:
        cuencas_service.create_cuenca(cuenca)
        pass
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")
