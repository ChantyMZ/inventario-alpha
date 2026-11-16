from abc import ABC, abstractmethod


# Interfaz base para todos los observadores
class Observer(ABC):
    @abstractmethod
    def actualizar(self, producto):
        pass


# Interfaz base para el sujeto que notifica
class Subject(ABC):
    @abstractmethod
    def agregar_observer(self, observer):
        pass

    @abstractmethod
    def notificar_observers(self, producto):
        pass


# Observador concreto: revisa si el producto quedó en su mínimo o por debajo
class AlertaStockObserver(Observer):
    def __init__(self):
        self.alertas = []

    def actualizar(self, producto):
        if producto['stock'] > producto['stock_minimo']:
            return
        if producto['stock'] == 0:
            mensaje = f"Se agotó: {producto['nombre']}. Hay que reponerlo."
        else:
            mensaje = (f"Quedan {producto['stock']} de {producto['nombre']} "
                       f"y el mínimo es {producto['stock_minimo']}. Hay que reponerlo.")
        self.alertas.append(mensaje)

    def get_alertas(self):
        alertas = self.alertas.copy()
        self.alertas = []  # limpiamos después de leerlas
        return alertas


# Sujeto concreto: el inventario que notifica cuando cambia un producto
class Inventario(Subject):
    def __init__(self):
        self._observers = []

    def agregar_observer(self, observer):
        self._observers.append(observer)

    def notificar_observers(self, producto):
        for observer in self._observers:
            observer.actualizar(producto)
