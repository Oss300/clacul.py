


"""
Calculadora de Tabla de Verdad + Procedimiento con Leyes Lógicas
Ejecutar con:  streamlit run calculadora_completa.py
"""
import heapq
import html
import itertools
import re
import time

import pandas as pd
import streamlit as st

# ============================================================
# 1. PARSER (sin eval)
# Precedencia (mayor a menor): ¬ > ∧ > ∨ > ⊕ > → > ↔
# Árbol: ("var", "p") | ("const", True) | ("not", x) | (op, a, b)
# ============================================================
TOKENS = [
    ("IFF", r"<->|<=>|↔"),
    ("IMP", r"->|=>|→"),
    ("XOR", r"⊕|\bXOR\b"),
    ("AND", r"∧|&&|&|\bAND\b"),
    ("OR", r"∨|\|\||\||\bOR\b"),
    ("NOT", r"¬|~|!|\bNOT\b"),
    ("LP", r"[(\[{]"),   # abre: ( [ {
    ("RP", r"[)\]}]"),   # cierra: ) ] }
    ("CONST", r"\b[01]\b"),
    ("VAR", r"[A-Za-z_][A-Za-z0-9_]*"),
    ("WS", r"\s+"),
]
REGEX = re.compile("|".join(f"(?P<{n}>{p})" for n, p in TOKENS), re.IGNORECASE)
SIMBOLO = {"and": "∧", "or": "∨", "xor": "⊕", "imp": "→", "iff": "↔"}


class ErrorSintaxis(Exception):
    pass


def tokenizar(texto):
    pos, out = 0, []
    while pos < len(texto):
        m = REGEX.match(texto, pos)
        if not m:
            raise ErrorSintaxis(f"Carácter no reconocido: '{texto[pos]}' (posición {pos + 1})")
        pos = m.end()
        if m.lastgroup != "WS":
            out.append((m.lastgroup, m.group()))
    _validar_agrupadores(out)
    return out


PAR = {"(": ")", "[": "]", "{": "}"}


def _validar_agrupadores(tokens):
    """Revisa que ( [ { se cierren con su pareja correcta y en el orden correcto."""
    pila = []
    for k, (tipo, txt) in enumerate(tokens):
        if tipo == "LP":
            pila.append(txt)
        elif tipo == "RP":
            if not pila:
                raise ErrorSintaxis(f"Sobra el '{txt}': no hay nada que cerrar.")
            esperado = PAR[pila[-1]]
            if txt != esperado:
                raise ErrorSintaxis(
                    f"Se esperaba '{esperado}' para cerrar '{pila[-1]}', pero se encontró '{txt}'.")
            pila.pop()
            if tokens[k - 1][0] == "LP":
                raise ErrorSintaxis(f"Hay un grupo vacío: '{tokens[k - 1][1]}{txt}'.")
    if pila:
        faltan = " ".join(PAR[x] for x in reversed(pila))
        raise ErrorSintaxis(f"Falta cerrar: {faltan}")


class Parser:
    def __init__(self, tokens):
        self.t, self.i = tokens, 0

    def _ver(self):
        return self.t[self.i][0] if self.i < len(self.t) else None

    def _tomar(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def parsear(self):
        if not self.t:
            raise ErrorSintaxis("La expresión está vacía.")
        nodo = self._iff()
        if self.i < len(self.t):
            raise ErrorSintaxis(f"Símbolo inesperado: '{self.t[self.i][1]}'")
        return nodo

    def _iff(self):
        izq = self._imp()
        while self._ver() == "IFF":
            self._tomar()
            izq = ("iff", izq, self._imp())
        return izq

    def _imp(self):  # asociativa a la derecha
        izq = self._xor()
        if self._ver() == "IMP":
            self._tomar()
            return ("imp", izq, self._imp())
        return izq

    def _xor(self):
        izq = self._or()
        while self._ver() == "XOR":
            self._tomar()
            izq = ("xor", izq, self._or())
        return izq

    def _or(self):
        izq = self._and()
        while self._ver() == "OR":
            self._tomar()
            izq = ("or", izq, self._and())
        return izq

    def _and(self):
        izq = self._not()
        while self._ver() == "AND":
            self._tomar()
            izq = ("and", izq, self._not())
        return izq

    def _not(self):
        if self._ver() == "NOT":
            self._tomar()
            return ("not", self._not())
        return self._atomo()

    def _atomo(self):
        v = self._ver()
        if v == "VAR":
            return ("var", self._tomar()[1])
        if v == "CONST":
            return ("const", self._tomar()[1] == "1")
        if v == "LP":
            abre = self._tomar()[1]
            nodo = self._iff()
            if self._ver() != "RP":
                raise ErrorSintaxis(f"Falta cerrar '{abre}' con '{PAR[abre]}'.")
            self._tomar()
            return nodo
        if v is None:
            raise ErrorSintaxis("La expresión termina de forma inesperada.")
        raise ErrorSintaxis(f"Símbolo inesperado: '{self.t[self.i][1]}'")


def parsear(texto):
    return Parser(tokenizar(texto)).parsear()


def variables(nodo, acc=None):
    """Variables en orden de aparición."""
    acc = [] if acc is None else acc
    if nodo[0] == "var":
        if nodo[1] not in acc:
            acc.append(nodo[1])
    elif nodo[0] != "const":
        for hijo in nodo[1:]:
            variables(hijo, acc)
    return acc


def evaluar(nodo, env):
    k = nodo[0]
    if k == "var":
        return env[nodo[1]]
    if k == "const":
        return nodo[1]
    if k == "not":
        return not evaluar(nodo[1], env)
    a, b = evaluar(nodo[1], env), evaluar(nodo[2], env)
    return {
        "and": a and b,
        "or": a or b,
        "xor": a != b,
        "imp": (not a) or b,
        "iff": a == b,
    }[k]


AGRUPADORES = [("(", ")"), ("[", "]"), ("{", "}")]


ASOCIATIVOS = ("and", "or", "xor", "iff")


def _cadena(nodo):
    """True si el hijo izquierdo repite el mismo operador asociativo: a ∧ b ∧ c
    (el parser agrupa a la izquierda, así que no hace falta agrupador)."""
    return nodo[0] in ASOCIATIVOS and nodo[1][0] == nodo[0]


def _interior(nodo):
    """Niveles de agrupación dentro del texto del nodo, sin contar el suyo."""
    if nodo[0] in ("var", "const"):
        return 0
    if nodo[0] == "not":
        return _nivel(nodo[1])
    izq = _interior(nodo[1]) if _cadena(nodo) else _nivel(nodo[1])
    return max(izq, _nivel(nodo[2]))


def _nivel(nodo):
    """Niveles de agrupación que necesita mostrar este nodo (0 si ninguno)."""
    k = nodo[0]
    if k in ("var", "const"):
        return 0
    if k == "not":
        return _nivel(nodo[1])
    return 1 + _interior(nodo)


def a_texto(nodo, raiz=True):
    """Texto de la expresión. Agrupadores como en los libros: ( ) el grupo más
    interno, [ ] el que lo contiene, { } el siguiente, y vuelve a empezar."""
    k = nodo[0]
    if k == "var":
        return nodo[1]
    if k == "const":
        return "1" if nodo[1] else "0"
    if k == "not":
        return "¬" + a_texto(nodo[1], False)
    izq = a_texto(nodo[1], _cadena(nodo))  # en cadena: sin agrupador extra
    s = f"{izq} {SIMBOLO[k]} {a_texto(nodo[2], False)}"
    if raiz:
        return s
    abre, cierra = AGRUPADORES[(_nivel(nodo) - 1) % 3]
    return f"{abre}{s}{cierra}"


def subexpresiones(nodo, acc=None):
    """Subexpresiones no triviales, de adentro hacia afuera, sin repetir."""
    acc = [] if acc is None else acc
    if nodo[0] in ("var", "const"):
        return acc
    for hijo in nodo[1:]:
        subexpresiones(hijo, acc)
    if nodo not in acc:
        acc.append(nodo)
    return acc


def equivalentes(a, b):
    """Compara dos árboles fila por fila con la tabla de verdad."""
    vs = variables(a)
    for v in variables(b):
        if v not in vs:
            vs.append(v)
    return all(
        evaluar(a, dict(zip(vs, vals))) == evaluar(b, dict(zip(vs, vals)))
        for vals in itertools.product([True, False], repeat=len(vs))
    )


def tabla_de_verdad(arbol, paso_a_paso=True, max_vars=6):
    """Devuelve (filas, columnas, clasificación). Cada fila es lista de bools."""
    vs = variables(arbol)
    if len(vs) > max_vars:
        raise ErrorSintaxis(f"Máximo {max_vars} variables (tienes {len(vs)}).")
    subs = subexpresiones(arbol) if paso_a_paso else []
    if arbol not in subs:
        subs.append(arbol)
    nombres = [a_texto(s) for s in subs]
    if arbol[0] in ("var", "const"):  # evita columna duplicada (p | p)
        nombres[-1] = "Resultado"
    filas = []
    for valores in itertools.product([True, False], repeat=len(vs)):
        env = dict(zip(vs, valores))
        filas.append(list(valores) + [evaluar(s, env) for s in subs])
    resultado = [f[-1] for f in filas]
    if all(resultado):
        clase = "tautología"
    elif not any(resultado):
        clase = "contradicción"
    else:
        clase = "contingencia"
    return filas, vs + nombres, clase


# ============================================================
# 2. LEYES LÓGICAS (reescritura paso a paso)
# Cada regla devuelve (nuevo_nodo, nombre_de_la_ley) o None.
# ============================================================
def _neg(x):
    return ("not", x)


def _canon(n):
    """Forma canónica: ordena operandos de ∧ ∨ ⊕ ↔ (conmutatividad)."""
    k = n[0]
    if k in ("var", "const"):
        return n
    if k == "not":
        return ("not", _canon(n[1]))
    hijos = [_canon(n[1]), _canon(n[2])]
    if k != "imp":
        hijos.sort(key=repr)
    return (k, *hijos)


def _iguales(a, b):
    return _canon(a) == _canon(b)


def _complementarios(a, b):
    return _iguales(a, _neg(b)) or _iguales(_neg(a), b)


def _aplanar(n, op):
    """(a ∨ b) ∨ c  ->  [a, b, c]"""
    if n[0] == op:
        return _aplanar(n[1], op) + _aplanar(n[2], op)
    return [n]


def _anidar(op, terminos):
    """[a, b, c] -> a op (b op c)"""
    t = terminos[-1]
    for x in reversed(terminos[:-1]):
        t = (op, x, t)
    return t


def _reconstruir(n, op, reemplazos):
    """Reconstruye n conservando su forma; reemplaza términos por índice."""
    cont = [0]

    def rec(x):
        if x[0] == op:
            return (op, rec(x[1]), rec(x[2]))
        i = cont[0]
        cont[0] += 1
        return reemplazos.get(i, x)

    return rec(n)


# --- Grupo 1: eliminar ↔, ⊕, → --------------------------------
def _eliminar_iff(n):
    if n[0] == "iff":
        a, b = n[1], n[2]
        return (("and", ("imp", a, b), ("imp", b, a)),
                "Bicondicional (p ↔ q ≡ (p → q) ∧ (q → p))")


def _eliminar_xor(n):
    if n[0] == "xor":
        a, b = n[1], n[2]
        return (("and", ("or", a, b), _neg(("and", a, b))),
                "XOR (p ⊕ q ≡ (p ∨ q) ∧ ¬(p ∧ q))")


def _eliminar_imp(n):
    if n[0] == "imp":
        return ("or", _neg(n[1]), n[2]), "Condicional (p → q ≡ ¬p ∨ q)"


# --- Grupo 2: mover las negaciones hacia adentro ---------------
def _doble_neg(n):
    if n[0] == "not" and n[1][0] == "not":
        return n[1][1], "Doble negación (¬¬p ≡ p)"


def _morgan(n):
    if n[0] == "not" and n[1][0] in ("and", "or"):
        k, a, b = n[1]
        if k == "and":
            return ("or", _neg(a), _neg(b)), "De Morgan (¬(p ∧ q) ≡ ¬p ∨ ¬q)"
        return ("and", _neg(a), _neg(b)), "De Morgan (¬(p ∨ q) ≡ ¬p ∧ ¬q)"


def _neg_constante(n):
    if n[0] == "not" and n[1][0] == "const":
        return ("const", not n[1][1]), "Negación de constante (¬1 ≡ 0, ¬0 ≡ 1)"


# --- Grupo 3: simplificar --------------------------------------
def _simplificar(n):
    k = n[0]
    if k not in ("and", "or"):
        return None
    a, b = n[1], n[2]
    s = SIMBOLO[k]
    otro = "and" if k == "or" else "or"
    s_otro = SIMBOLO[otro]
    dom = k == "or"  # constante que domina: 1 en ∨, 0 en ∧
    d, i = ("1", "0") if k == "or" else ("0", "1")

    for x, y in ((a, b), (b, a)):
        if x == ("const", dom):
            return x, f"Dominación (p {s} {d} ≡ {d})"
        if x == ("const", not dom):
            return y, f"Identidad (p {s} {i} ≡ p)"
    if _complementarios(a, b):
        return ("const", dom), f"Complemento (p {s} ¬p ≡ {d})"
    if _iguales(a, b):
        return a, f"Idempotencia (p {s} p ≡ p)"
    for x, y in ((a, b), (b, a)):
        if y[0] == otro and any(_iguales(x, z) for z in y[1:]):
            return x, f"Absorción (p {s} (p {s_otro} q) ≡ p)"


def _absorcion_general(n):
    """Con varios términos: p ∨ r ∨ (¬p ∧ q)  ≡  p ∨ r ∨ q   y   p ∨ r ∨ (p ∧ q) ≡ p ∨ r."""
    k = n[0]
    if k not in ("and", "or"):
        return None
    otro = "and" if k == "or" else "or"
    s, s_otro = SIMBOLO[k], SIMBOLO[otro]
    t = _aplanar(n, k)
    if len(t) < 2:
        return None
    for i, term in enumerate(t):
        if term[0] != otro:
            continue
        factores = _aplanar(term, otro)
        for fi, f in enumerate(factores):
            for j, u in enumerate(t):
                if j == i:
                    continue
                if _iguales(f, u):  # absorción: se elimina el término completo
                    resto = [x for m, x in enumerate(t) if m != i]
                    return (_anidar(k, resto),
                            f"Absorción (p {s} (p {s_otro} q) ≡ p)")
                if _complementarios(f, u):  # se elimina solo el factor
                    nuevo = _anidar(otro, [x for m, x in enumerate(factores) if m != fi])
                    return (_reconstruir(n, k, {i: nuevo}),
                            f"Absorción generalizada (p {s} (¬p {s_otro} q) ≡ p {s} q)")


def _factor_comun(n):
    """(p ∨ q) ∧ (p ∨ ¬q) ≡ p ∨ (q ∧ ¬q)   y   (p ∧ q) ∨ (p ∧ ¬q) ≡ p ∧ (q ∨ ¬q)."""
    k = n[0]
    if k not in ("and", "or"):
        return None
    otro = "and" if k == "or" else "or"
    a, b = n[1], n[2]
    if a[0] != otro or b[0] != otro:
        return None
    for xi in (1, 2):
        for yi in (1, 2):
            x, y = a[xi], b[yi]
            if _iguales(x, y):
                ra, rb = a[3 - xi], b[3 - yi]
                if _complementarios(ra, rb) or _iguales(ra, rb):
                    return ((otro, x, (k, ra, rb)),
                            f"Distributiva ((p {SIMBOLO[otro]} q) {SIMBOLO[k]} "
                            f"(p {SIMBOLO[otro]} r) ≡ p {SIMBOLO[otro]} (q {SIMBOLO[k]} r))")


# --- Grupo 4: reagrupar para que dos términos queden juntos ----
def _reordenar(n):
    k = n[0]
    if k not in ("and", "or"):
        return None
    t = _aplanar(n, k)
    for i in range(len(t)):
        for j in range(i + 1, len(t)):
            if _iguales(t[i], t[j]) or _complementarios(t[i], t[j]):
                resto = [x for m, x in enumerate(t) if m not in (i, j)]
                nuevo = _anidar(k, resto + [(k, t[i], t[j])])
                if nuevo == n:
                    continue
                ley = "Asociativa" if resto + [t[i], t[j]] == t else "Conmutativa y asociativa"
                return nuevo, f"{ley} (agrupar términos para simplificar)"


# Se prueba el grupo 1; si no aplica nada, el 2; y así. Tras cada paso se
# vuelve a empezar por el grupo 1.
GRUPOS = [
    [_eliminar_iff, _eliminar_xor, _eliminar_imp],
    [_doble_neg, _morgan, _neg_constante],
    [_simplificar, _absorcion_general, _factor_comun],
    [_reordenar],
]


def _buscar(nodo, reglas):
    """Primera regla aplicable, recorriendo de adentro hacia afuera.
    Devuelve (nodo_nuevo, ley, parte_antes, parte_despues): la parte que cambió."""
    if nodo[0] not in ("var", "const"):
        for i in range(1, len(nodo)):
            r = _buscar(nodo[i], reglas)
            if r:
                hijo, ley, antes, despues = r
                return nodo[:i] + (hijo,) + nodo[i + 1:], ley, antes, despues
    for regla in reglas:
        r = regla(nodo)
        if r:
            return r[0], r[1], nodo, r[0]
    return None


def derivar_detalle(arbol, max_pasos=80):
    """Devuelve [(ley, nodo, antes, despues), ...]. El primer elemento es la
    expresión original (ley=None). 'antes' y 'despues' son solo la parte de la
    expresión sobre la que se aplicó la ley."""
    pasos = [(None, arbol, None, None)]
    vistos = {arbol}
    actual = arbol
    for _ in range(max_pasos):
        r = None
        for grupo in GRUPOS:
            r = _buscar(actual, grupo)
            if r:
                break
        if not r:
            break
        actual, ley, antes, despues = r
        if actual in vistos:  # protección contra ciclos
            break
        vistos.add(actual)
        pasos.append((ley, actual, antes, despues))
    return pasos


def derivar(arbol, max_pasos=80):
    """Devuelve [(ley, nodo), ...]. El primer elemento es la original (ley=None)."""
    return [(ley, nodo) for ley, nodo, _, _ in derivar_detalle(arbol, max_pasos)]


# --- Búsqueda del camino más corto ------------------------------
# derivar_detalle sigue un orden fijo (clásico: quitar flechas, mover
# negaciones, simplificar). Aquí se prueban TODAS las formas de aplicar una ley
# en cualquier parte y se elige la secuencia con menos pasos hasta el resultado.
def _tamano(n):
    return 1 if n[0] in ("var", "const") else 1 + sum(_tamano(h) for h in n[1:])


def _objetivo(arbol):
    """1 si es tautología, 0 si es contradicción, None si es contingencia."""
    vs = variables(arbol)
    if len(vs) > 8:
        return None
    r = [evaluar(arbol, dict(zip(vs, v))) for v in itertools.product([True, False], repeat=len(vs))]
    if all(r):
        return ("const", True)
    if not any(r):
        return ("const", False)
    return None


def _aplicaciones(nodo, g):
    """Todas las formas de aplicar UNA ley del grupo g, en cualquier parte del nodo."""
    if nodo[0] not in ("var", "const"):
        for i in range(1, len(nodo)):
            for hijo, ley, antes, despues in _aplicaciones(nodo[i], g):
                yield nodo[:i] + (hijo,) + nodo[i + 1:], ley, antes, despues
    for regla in GRUPOS[g]:
        r = regla(nodo)
        if r:
            yield r[0], r[1], nodo, r[0]


def derivar_corto(arbol, max_estados=4000, max_pasos=30, limite_seg=1.5):
    """Camino con menos pasos (mismo formato que derivar_detalle).
    Si la expresión es tautología/contradicción el destino es 1/0; si no, la
    expresión más pequeña que se alcance. Un pequeño costo extra desempata a
    favor de las leyes de simplificación sobre los reagrupamientos."""
    objetivo = _objetivo(arbol)
    inicio = _canon(arbol)
    cont = itertools.count()
    heap = [(0.0, 0, next(cont), arbol)]
    dist = {inicio: 0.0}
    padre = {inicio: None}
    mejor = (_tamano(arbol), 0.0, inicio)
    meta = None
    expandidos = 0
    tam_max = 3 * _tamano(arbol) + 10  # no explorar expresiones que se disparan de tamaño
    limite = time.monotonic() + limite_seg
    while heap and expandidos < max_estados and time.monotonic() < limite:
        coste, pasos, _, nodo = heapq.heappop(heap)
        clave = _canon(nodo)
        if coste > dist[clave]:
            continue  # entrada vieja: ya se llegó aquí por un camino mejor
        if objetivo is not None and nodo == objetivo:
            meta = clave
            break
        cand = (_tamano(nodo), coste, clave)
        if cand[:2] < mejor[:2]:
            mejor = cand
        expandidos += 1
        if pasos >= max_pasos:
            continue
        for g in range(len(GRUPOS)):
            for nuevo, ley, antes, despues in _aplicaciones(nodo, g):
                if _tamano(nuevo) > tam_max:
                    continue
                k = _canon(nuevo)
                c = coste + 1 + 0.01 * g
                if k not in dist or c < dist[k]:
                    dist[k] = c
                    padre[k] = (clave, ley, antes, despues, nuevo)
                    heapq.heappush(heap, (c, pasos + 1, next(cont), nuevo))
    meta = meta or mejor[2]
    camino = []
    k = meta
    while padre[k] is not None:
        previa, ley, antes, despues, nuevo = padre[k]
        camino.append((ley, nuevo, antes, despues))
        k = previa
    return [(None, arbol, None, None)] + camino[::-1]


def derivar_mejor(arbol):
    """El camino más corto; si el clásico es igual de bueno, se queda con el clásico."""
    clasico = derivar_detalle(arbol)
    try:
        corto = derivar_corto(arbol)
    except Exception:  # por seguridad: nunca dejar sin respuesta
        return clasico
    tam_c, tam_k = _tamano(clasico[-1][1]), _tamano(corto[-1][1])
    if tam_k < tam_c or (tam_k == tam_c and len(corto) < len(clasico)):
        return corto
    return clasico


# ============================================================
# 2b. REFERENCIA Y EXPLICACIÓN DE LAS LEYES
# ============================================================
# (nombre, equivalencias, qué dice, ejemplo)
LEYES_REF = [
    ("Condicional", "p → q ≡ ¬p ∨ q",
     "Una implicación solo es falsa si p es verdadero y q falso, igual que ¬p ∨ q. "
     "Sirve para eliminar la flecha.",
     "(p → ¬q)  pasa a  (¬p ∨ ¬q)"),
    ("Bicondicional", "p ↔ q ≡ (p → q) ∧ (q → p)",
     "Es verdadero cuando ambos valen lo mismo: p implica q y q implica p.",
     "p ↔ q  pasa a  (p → q) ∧ (q → p)"),
    ("XOR", "p ⊕ q ≡ (p ∨ q) ∧ ¬(p ∧ q)",
     "Es verdadero cuando al menos uno es verdadero, pero no los dos a la vez.",
     "p ⊕ q  pasa a  (p ∨ q) ∧ ¬(p ∧ q)"),
    ("Doble negación", "¬¬p ≡ p",
     "Negar dos veces devuelve el valor original.",
     "¬¬q  pasa a  q"),
    ("De Morgan", "¬(p ∧ q) ≡ ¬p ∨ ¬q\n¬(p ∨ q) ≡ ¬p ∧ ¬q",
     "Al negar un grupo, la negación entra en él y cambia ∧ por ∨ (o ∨ por ∧).",
     "¬(p ∨ q)  pasa a  ¬p ∧ ¬q"),
    ("Negación de constante", "¬1 ≡ 0\n¬0 ≡ 1",
     "La negación de verdadero es falso y la de falso es verdadero.",
     "¬1  pasa a  0"),
    ("Identidad", "p ∧ 1 ≡ p\np ∨ 0 ≡ p",
     "El elemento neutro no cambia nada: ∧ con 1 o ∨ con 0 deja la expresión igual.",
     "q ∧ 1  pasa a  q"),
    ("Dominación", "p ∨ 1 ≡ 1\np ∧ 0 ≡ 0",
     "Una constante dominante fija todo el resultado: ∨ con 1 da 1 y ∧ con 0 da 0.",
     "q ∨ 1  pasa a  1"),
    ("Complemento", "p ∨ ¬p ≡ 1\np ∧ ¬p ≡ 0",
     "Una expresión junto a su negación: con ∨ siempre da 1 y con ∧ siempre da 0.",
     "q ∨ ¬q  pasa a  1"),
    ("Idempotencia", "p ∧ p ≡ p\np ∨ p ≡ p",
     "Repetir la misma expresión con ∧ o con ∨ no añade nada.",
     "p ∨ p  pasa a  p"),
    ("Absorción", "p ∨ (p ∧ q) ≡ p\np ∧ (p ∨ q) ≡ p",
     "Si p aparece solo y también dentro del grupo con q, el grupo sobra y queda p.",
     "p ∧ (p ∨ q)  pasa a  p"),
    ("Absorción generalizada", "p ∨ (¬p ∧ q) ≡ p ∨ q\np ∧ (¬p ∨ q) ≡ p ∧ q",
     "Si en el grupo aparece ¬p y p está afuera, se puede quitar ¬p del grupo.",
     "p ∨ (¬p ∧ q)  pasa a  p ∨ q"),
    ("Distributiva", "(p ∨ q) ∧ (p ∨ r) ≡ p ∨ (q ∧ r)\n(p ∧ q) ∨ (p ∧ r) ≡ p ∧ (q ∨ r)",
     "Si dos grupos comparten el factor p, se saca p como factor común.",
     "(p ∨ q) ∧ (p ∨ ¬q)  pasa a  p ∨ (q ∧ ¬q)"),
    ("Asociativa", "(p ∧ q) ∧ r ≡ p ∧ (q ∧ r)\n(p ∨ q) ∨ r ≡ p ∨ (q ∨ r)",
     "Con el mismo operador, cambiar los agrupadores no cambia el valor. Se usa para "
     "juntar los términos que se van a simplificar.",
     "(p ∨ q) ∨ ¬p  pasa a  q ∨ (p ∨ ¬p)"),
    ("Conmutativa", "p ∧ q ≡ q ∧ p\np ∨ q ≡ q ∨ p",
     "El orden de los términos con el mismo operador no cambia el valor.",
     "p ∨ q ∨ ¬p  pasa a  q ∨ (p ∨ ¬p)"),
]

POR_QUE = {
    "Bicondicional": "p ↔ q es verdadero cuando ambos valen lo mismo, es decir, cuando p implica q y q implica p.",
    "XOR": "p ⊕ q es verdadero cuando al menos uno lo es, pero no los dos a la vez.",
    "Condicional": "p → q solo es falso cuando p es verdadero y q falso, igual que ¬p ∨ q. Así se elimina la flecha.",
    "Doble negación": "Negar dos veces devuelve el valor original, así que las dos negaciones se cancelan.",
    "De Morgan": "Al negar un grupo, la negación entra en él y el operador cambia: ∧ pasa a ∨ y ∨ pasa a ∧.",
    "Negación de constante": "La negación de 1 es 0 y la de 0 es 1.",
    "Dominación": "Una constante dominante decide todo el resultado: ∨ con 1 da 1 y ∧ con 0 da 0.",
    "Identidad": "El elemento neutro no cambia nada: ∧ con 1 o ∨ con 0 deja la expresión igual.",
    "Complemento": "Una expresión junto a su negación: con ∨ siempre da 1 y con ∧ siempre da 0.",
    "Idempotencia": "Repetir la misma expresión con ∧ o con ∨ no añade nada, así que basta una vez.",
    "Absorción": "Como la expresión aparece sola y también dentro del grupo, el grupo sobra.",
    "Absorción generalizada": "La expresión está afuera y su negación dentro del grupo; esa negación se puede quitar del grupo.",
    "Distributiva": "Los dos grupos comparten un factor, así que se saca como factor común.",
    "Asociativa": "Con el mismo operador, cambiar los agrupadores no cambia el valor. Se hace para juntar los términos que se van a simplificar.",
    "Conmutativa y asociativa": "Se reordenan y reagrupan los términos del mismo operador para acercar los que se simplifican.",
}


def nombre_ley(ley):
    """'Condicional (p → q ≡ ¬p ∨ q)' -> 'Condicional'."""
    return ley.partition(" (")[0]


def leyes_usadas(pasos):
    """Nombres (de LEYES_REF) usados en una derivación, en orden de aparición."""
    usadas = []
    for paso in pasos[1:]:
        nombre = nombre_ley(paso[0])
        for n in (["Conmutativa", "Asociativa"] if nombre == "Conmutativa y asociativa" else [nombre]):
            if n not in usadas:
                usadas.append(n)
    return usadas


def explicar_paso(ley, antes, despues):
    """Explicación en lenguaje sencillo de un paso del procedimiento."""
    nombre = nombre_ley(ley)
    return (f"En «{a_texto(antes)}» se aplica la ley «{nombre}». "
            f"{POR_QUE.get(nombre, '')} Queda «{a_texto(despues)}».")


def explicar_procedimiento(pasos, camino_corto=False):
    """Resumen en una o dos frases de todo el procedimiento."""
    n = len(pasos) - 1
    if n == 0:
        return "La expresión ya está simplificada: no se pudo aplicar ninguna ley."
    leyes = leyes_usadas(pasos)
    final = pasos[-1][1]
    if final == ("const", True):
        cierre = "El resultado es 1, así que la expresión es una tautología."
    elif final == ("const", False):
        cierre = "El resultado es 0, así que la expresión es una contradicción."
    else:
        cierre = f"La forma simplificada es «{a_texto(final)}»."
    metodo = ("Se eligió el camino con menos pasos entre todas las leyes aplicables."
              if camino_corto else
              "Primero se eliminan ↔, ⊕ y →, luego se llevan las negaciones hacia adentro y "
              "después se simplifica.")
    return (f"Se necesitaron {n} paso{'s' if n != 1 else ''} usando: {', '.join(leyes)}. "
            f"{metodo} {cierre}")


# ============================================================
# 3. INTERFAZ (estilo calculadora: pantalla, teclado y pasos en tarjetas)
# La lógica de arriba no depende de esta parte.
# ============================================================
BINARIOS = {"IFF": "↔", "IMP": "→", "XOR": "⊕", "AND": "∧", "OR": "∨"}


def normalizar(texto):
    """Expresión tal como la escribió la persona (conserva ( ) [ ] { }),
    pero con los símbolos unificados: ~ → ¬, & → ∧, -> → →, etc."""
    salida = ""
    for tipo, txt in tokenizar(texto):
        if tipo in BINARIOS:
            salida += f" {BINARIOS[tipo]} "
        elif tipo == "NOT":
            salida += "¬"
        else:
            salida += txt
    return salida.strip()


CSS = """
<style>
.block-container{max-width:1250px;padding-top:1.2rem}
.hero{background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;padding:1.1rem 1.5rem;
      border-radius:18px;margin-bottom:1.1rem}
.hero h1{margin:0;font-size:1.65rem;color:#fff}
.hero p{margin:.3rem 0 0;opacity:.92}

/* Pantalla (cuadro de texto) */
div[data-testid="stTextInput"] input{font-family:ui-monospace,Consolas,Menlo,monospace;
  font-size:1.55rem;padding:.85rem 1rem;border-radius:16px;border:2px solid rgba(99,102,241,.45)}
div[data-testid="stTextInput"] input:focus{border-color:#6366f1;box-shadow:0 0 0 3px rgba(99,102,241,.2)}
.estado{font-size:.9rem;margin:.1rem 0 .7rem;padding-left:.3rem}
.estado.ok{color:#059669}.estado.mal{color:#dc2626}.estado.vacio{opacity:.6}

/* Teclado */
.stButton>button,.stDownloadButton>button{width:100%;border-radius:14px;font-size:1.2rem;
  font-weight:600;padding:.55rem 0;border:1px solid rgba(127,127,127,.3);transition:all .12s}
.stButton>button:hover{transform:translateY(-1px);border-color:#6366f1;color:#6366f1}
[class*="st-key-var_"] button,[class*="st-key-const_"] button{background:rgba(99,102,241,.13)}
[class*="st-key-op_"] button{background:rgba(139,92,246,.16)}
[class*="st-key-agr_"] button{background:rgba(245,158,11,.18)}
[class*="st-key-act_"] button{background:rgba(239,68,68,.15)}
[class*="st-key-ej_"] button{font-size:.95rem;font-weight:500;justify-content:flex-start;
  font-family:ui-monospace,Consolas,monospace;padding:.4rem .8rem}
[class*="st-key-resolver"] button{background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;
  border:none;font-size:1.2rem;padding:.85rem 0}
[class*="st-key-resolver"] button:hover{color:#fff;filter:brightness(1.08)}

/* Resultados */
.pantalla{font-family:ui-monospace,Consolas,Menlo,monospace;font-size:1.7rem;padding:1rem 1.2rem;
  border-radius:16px;background:rgba(99,102,241,.1);border:1px solid rgba(99,102,241,.3);
  overflow-x:auto;white-space:nowrap}
.chips{margin:.6rem 0 1rem}
.badge{display:inline-block;padding:.3rem .9rem;border-radius:999px;font-weight:700;
  font-size:.92rem;margin-right:.5rem}
.badge.taut{background:rgba(16,185,129,.2);color:#059669}
.badge.contra{background:rgba(239,68,68,.2);color:#dc2626}
.badge.conti{background:rgba(99,102,241,.2);color:#6366f1}
.badge.var{background:rgba(127,127,127,.15)}
.step{display:flex;gap:.9rem;align-items:flex-start;border:1px solid rgba(127,127,127,.28);
  border-radius:14px;padding:.8rem 1rem;margin-bottom:.6rem;background:rgba(127,127,127,.05)}
.step .n{flex:0 0 2rem;height:2rem;border-radius:50%;background:rgba(99,102,241,.2);color:#6366f1;
  font-weight:700;display:flex;align-items:center;justify-content:center}
.step .expr{font-family:ui-monospace,Consolas,Menlo,monospace;font-size:1.3rem;overflow-x:auto}
.step .ley{display:inline-block;margin-top:.4rem;background:rgba(127,127,127,.15);
  border-radius:999px;padding:.2rem .8rem;font-size:.85rem}
.step .ley code{background:none;font-size:.85rem}
.step.orig .n{background:rgba(127,127,127,.25);color:inherit}
.step.final.ok{border-color:#10b981;background:rgba(16,185,129,.1)}
.step.final.bad{border-color:#ef4444;background:rgba(239,68,68,.1)}
.step.final.neu{border-color:#6366f1;background:rgba(99,102,241,.1)}
.vacio-res{text-align:center;padding:3rem 1rem;opacity:.6;border:2px dashed rgba(127,127,127,.35);
  border-radius:18px}
.expl{margin-top:.5rem;font-size:.93rem;line-height:1.5;padding:.5rem .8rem;border-radius:10px;
  background:rgba(245,158,11,.12);border-left:4px solid #f59e0b}
.resumen{margin:.4rem 0 1rem;padding:.8rem 1rem;border-radius:14px;background:rgba(99,102,241,.1);
  border:1px solid rgba(99,102,241,.3);line-height:1.5}
.ref{width:100%;border-collapse:separate;border-spacing:0;border:1px solid rgba(127,127,127,.3);
  border-radius:14px;overflow:hidden}
.ref th{background:rgba(99,102,241,.2);text-align:left;padding:.65rem .85rem;font-size:.95rem}
.ref td{padding:.65rem .85rem;border-top:1px solid rgba(127,127,127,.2);vertical-align:top;font-size:.95rem}
.ref .eq{font-family:ui-monospace,Consolas,Menlo,monospace;white-space:pre-line}
.ref tr.usada td{background:rgba(16,185,129,.13)}
.ref tr.usada td:first-child{box-shadow:inset 4px 0 0 #10b981}
.ref .marca{display:inline-block;margin-left:.4rem;padding:.05rem .5rem;border-radius:999px;
  font-size:.75rem;background:rgba(16,185,129,.25);color:#059669;font-weight:700}
</style>
"""


def _tarjeta(n, expr, ley=None, clase="", explicacion=None):
    ley_html = ""
    if ley:
        nombre, _, formula = ley.partition(" (")
        if formula.endswith(")"):
            formula = formula[:-1]
        ley_html = (f'<span class="ley"><b>{html.escape(nombre)}</b>'
                    + (f' &nbsp;<code>{html.escape(formula)}</code>' if formula else "")
                    + "</span>")
    expl_html = f'<div class="expl">💡 {html.escape(explicacion)}</div>' if explicacion else ""
    return (f'<div class="step {clase}"><div class="n">{n}</div><div style="flex:1">'
            f'<div class="expr">{html.escape(expr)}</div>{ley_html}{expl_html}</div></div>')


def tabla_referencia(usadas=()):
    """Tabla fija: cada ley con las expresiones a las que se aplica.
    Las leyes usadas en el ejercicio actual salen resaltadas."""
    filas = []
    for nombre, equiv, significado, ejemplo in LEYES_REF:
        es_usada = nombre in usadas
        marca = '<span class="marca">usada</span>' if es_usada else ""
        filas.append(
            f'<tr class="{"usada" if es_usada else ""}">'
            f'<td><b>{html.escape(nombre)}</b>{marca}</td>'
            f'<td class="eq">{html.escape(equiv)}</td>'
            f'<td>{html.escape(significado)}</td>'
            f'<td class="eq">{html.escape(ejemplo)}</td></tr>')
    return ('<table class="ref"><thead><tr><th>Ley</th><th>Expresiones que cubre</th>'
            '<th>¿Qué dice?</th><th>Ejemplo</th></tr></thead><tbody>'
            + "".join(filas) + "</tbody></table>")


def mostrar_procedimiento(arbol, original, explicar=True, camino_corto=False):
    detalle = derivar_mejor(arbol) if camino_corto else derivar_detalle(arbol)
    pasos = [(ley, nodo) for ley, nodo, _, _ in detalle]
    final = pasos[-1][1]
    if final == ("const", True):
        clase_final = "ok"
    elif final == ("const", False):
        clase_final = "bad"
    else:
        clase_final = "neu"

    if explicar:
        st.markdown(f'<div class="resumen">🧭 <b>Resumen:</b> '
                    f'{html.escape(explicar_procedimiento(pasos, camino_corto))}</div>',
                    unsafe_allow_html=True)

    tarjetas = []
    for i, (ley, nodo, antes, despues) in enumerate(detalle):
        if i == 0:
            tarjetas.append(_tarjeta(0, original, "Expresión original", "orig"))
        else:
            es_ultimo = i == len(detalle) - 1
            expl = explicar_paso(ley, antes, despues) if explicar else None
            tarjetas.append(_tarjeta(i, a_texto(nodo), ley,
                                     f"final {clase_final}" if es_ultimo else "", expl))
    st.markdown("".join(tarjetas), unsafe_allow_html=True)

    if final == ("const", True):
        st.success("✅ Se reduce a **1** → tautología (siempre verdadera).")
    elif final == ("const", False):
        st.error("❌ Se reduce a **0** → contradicción (siempre falsa).")
    else:
        st.info(f"Forma simplificada: **{a_texto(final)}**. Si no llegó a 1 ni a 0 no significa "
                "que sea contingencia: confía en la tabla de verdad.")

    if equivalentes(arbol, final):
        st.caption("🔍 Verificado con la tabla de verdad: la expresión final es equivalente "
                   "a la original en todas las filas.")
    else:
        st.error("⚠️ La verificación falló: la expresión final no coincide con la original.")


def _color_celda(v):
    if v == 1:
        return "background-color:rgba(16,185,129,.25);color:#059669;font-weight:700;text-align:center"
    return "background-color:rgba(239,68,68,.2);color:#dc2626;font-weight:700;text-align:center"


def mostrar_tabla(arbol, paso_a_paso):
    filas, columnas, clase = tabla_de_verdad(arbol, paso_a_paso=paso_a_paso)
    df = pd.DataFrame([[int(x) for x in fila] for fila in filas], columns=columnas)
    resultados = df.iloc[:, -1].tolist()
    n_vars = len(variables(arbol))

    st.caption(f"Tabla de {len(filas)} filas · {n_vars} variable(s). Verde = 1, rojo = 0.")
    calculadas = columnas[n_vars:]
    estilo = df.style.set_properties(**{"text-align": "center"})
    aplicar = getattr(estilo, "map", None) or estilo.applymap  # pandas nuevo / antiguo
    estilo = aplicar(_color_celda, subset=calculadas)
    st.dataframe(estilo, hide_index=True)

    m1, m2, m3 = st.columns(3)
    m1.metric("Total de filas", len(filas))
    m2.metric("Verdaderos (1)", sum(resultados))
    m3.metric("Falsos (0)", len(filas) - sum(resultados))

    st.download_button("📥 Descargar CSV", df.to_csv(index=False).encode("utf-8"),
                       "tabla_verdad.csv", "text/csv")


def agregar(texto):
    st.session_state.expr += texto


def limpiar():
    st.session_state.expr = ""
    st.session_state.calc = ""


def borrar_ultimo():
    st.session_state.expr = st.session_state.expr.rstrip()[:-1]


def cargar(texto):
    st.session_state.expr = texto


EJEMPLOS = {
    "[(p ∨ q) ∧ ¬p] → q": "Ejercicio 7",
    "[(p → ¬q) → ¬p] → q": "Ejercicio 8",
    "[¬(p ∨ q) ∨ (¬p ∧ q)] → (¬p ∧ q)": "Ejercicio 9",
    "[(p → p) ∨ q] ∧ [¬q ∨ (r ∧ q)] ∧ [p → (p ∨ ¬q)]": "Ejercicio 10",
    "¬(p → q) → ¬q": "Ejercicio 11",
    "¬(p → ¬q) → q": "Se reduce a 1 (tautología)",
    "(p → q) ↔ (¬q → ¬p)": "Ley contrarrecíproca",
    "(p ∨ q) ∧ (p ∨ ¬q)": "Se reduce a p",
    "p ∧ (p → q)": "Se reduce a p ∧ q",
    "p ⊕ q": "XOR",
    "((p → q) ∧ (q → r)) → (p → r)": "Silogismo hipotético",
}


def teclado():
    """Teclado de la calculadora. Cada fila es un grupo de botones."""
    cols = st.columns(6)
    for i, v in enumerate(["p", "q", "r", "s", "t", "u"]):
        cols[i].button(v, key=f"var_{v}", on_click=agregar, args=(f" {v} ",))

    cols = st.columns(6)
    for i, (simbolo, nombre) in enumerate(
        [("∧", "AND"), ("∨", "OR"), ("¬", "NOT"), ("⊕", "XOR"), ("→", "IMPLIES"), ("↔", "IFF")]
    ):
        cols[i].button(simbolo, key=f"op_{nombre}", help=nombre, on_click=agregar,
                       args=(f" {simbolo} ",))

    cols = st.columns(6)
    for i, g in enumerate(["(", ")", "[", "]"]):
        cols[i].button(g, key=f"agr_{i}", on_click=agregar, args=(g,))
    cols[4].button("0", key="const_0", on_click=agregar, args=(" 0 ",))
    cols[5].button("1", key="const_1", on_click=agregar, args=(" 1 ",))

    c1, c2 = st.columns(2)
    c1.button("⌫  Borrar", key="act_borrar", on_click=borrar_ultimo)
    c2.button("🗑️  Limpiar", key="act_limpiar", on_click=limpiar)


def main():
    st.set_page_config(page_title="Calculadora de Tabla de Verdad", page_icon="🧮", layout="wide")
    st.markdown(CSS + """
<div class="hero"><h1>🧮 Calculadora de Tabla de Verdad</h1>
<p>Escribe o construye tu expresión · procedimiento paso a paso con leyes lógicas · tabla de verdad (0 y 1)</p>
</div>""", unsafe_allow_html=True)

    if "expr" not in st.session_state:
        st.session_state.expr = ""
    if "calc" not in st.session_state:
        st.session_state.calc = ""

    izq, der = st.columns([5, 7], gap="large")

    # ---------------- Columna izquierda: pantalla + teclado ----------------
    with izq:
        st.text_input("Expresión", key="expr", label_visibility="collapsed",
                      placeholder="Ej: [(p ∨ q) ∧ ¬p] → q")

        texto = st.session_state.expr.strip()
        if not texto:
            st.markdown('<div class="estado vacio">Usa el teclado o escribe: ~ & | -> <-> XOR también valen</div>',
                        unsafe_allow_html=True)
        else:
            try:
                vs = variables(parsear(texto))
                st.markdown(f'<div class="estado ok">✓ Expresión válida · variables: '
                            f'{html.escape(", ".join(vs)) or "ninguna"}</div>', unsafe_allow_html=True)
            except ErrorSintaxis as e:
                st.markdown(f'<div class="estado mal">✗ {html.escape(str(e))}</div>',
                            unsafe_allow_html=True)

        teclado()
        mostrar_pasos = st.checkbox("Mostrar subexpresiones en la tabla de verdad", value=True)
        explicar = st.checkbox("💡 Explicar cada paso del procedimiento", value=True)
        corto = st.checkbox("⚡ Buscar el camino más corto (si no, método clásico fijo)", value=True)

        if st.button("🚀  Resolver", key="resolver"):
            if not texto:
                st.warning("⚠️ Ingresa o construye una expresión primero.")
            else:
                st.session_state.calc = texto

        with st.expander("📋 Ejemplos y ejercicios"):
            for i, (expr, desc) in enumerate(EJEMPLOS.items()):
                st.button(expr, key=f"ej_{i}", help=desc, on_click=cargar, args=(expr,))

    # ---------------- Columna derecha: resultados ----------------
    usadas = []  # leyes usadas en el ejercicio actual (se resaltan en la tabla fija)
    with der:
        calc = st.session_state.calc
        if not calc:
            st.markdown('<div class="vacio-res">✍️<br><b>Aquí aparecerá la solución</b><br>'
                        'Escribe una expresión y pulsa <i>Resolver</i></div>', unsafe_allow_html=True)
        else:
            try:
                arbol = parsear(calc)
                _, _, clase = tabla_de_verdad(arbol, paso_a_paso=mostrar_pasos)  # valida
            except ErrorSintaxis as e:
                st.error(f"❌ {e}")
                st.info("Revisa operadores faltantes, agrupadores ( ) [ ] balanceados y que cada "
                        "operador tenga sus dos operandos.")
            else:
                original = normalizar(calc)  # conserva los ( ) [ ] que escribió la persona
                tipo = {"tautología": ("taut", "TAUTOLOGÍA · siempre verdadera"),
                        "contradicción": ("contra", "CONTRADICCIÓN · siempre falsa"),
                        "contingencia": ("conti", "CONTINGENCIA · depende de los valores")}[clase]
                vars_html = "".join(f'<span class="badge var">{html.escape(v)}</span>' for v in variables(arbol))
                st.markdown(f'<div class="pantalla">{html.escape(original)}</div>'
                            f'<div class="chips"><span class="badge {tipo[0]}">{tipo[1]}</span>{vars_html}</div>',
                            unsafe_allow_html=True)
                tab_leyes, tab_tabla = st.tabs(["📐 Procedimiento", "📊 Tabla de verdad"])
                camino = derivar_mejor(arbol) if corto else derivar_detalle(arbol)
                usadas = leyes_usadas(camino)
                with tab_leyes:
                    mostrar_procedimiento(arbol, original, explicar, corto)
                with tab_tabla:
                    mostrar_tabla(arbol, mostrar_pasos)

    # ---------------- Tabla fija de referencia de leyes ----------------
    st.markdown("---")
    st.subheader("📖 Tabla de referencia de leyes lógicas")
    st.caption("Qué expresiones cubre cada ley. Las leyes que se usaron en tu ejercicio "
               "aparecen resaltadas en verde." if usadas else
               "Qué expresiones cubre cada ley. Al resolver un ejercicio se resaltan las que usó.")
    st.markdown(tabla_referencia(usadas), unsafe_allow_html=True)

    st.markdown("---")
    g1, g2 = st.columns(2)
    with g1:
        with st.expander("📚 Guía de Operadores"):
            st.markdown("""
| Símbolo | Nombre | Significado |
|:-------:|:-------|:------------|
| **∧** | Conjunción | AND - Verdadero si AMBOS son verdaderos |
| **∨** | Disyunción | OR - Verdadero si al menos UNO es verdadero |
| **¬** | Negación | NOT - Invierte el valor |
| **⊕** | XOR | Verdadero si son DIFERENTES |
| **→** | Condicional | Falso solo si p=1 y q=0 |
| **↔** | Bicondicional | Verdadero si ambos son IGUALES |

**Precedencia (mayor a menor):** ¬, ∧, ∨, ⊕, →, ↔. Usa agrupadores `( )`, `[ ]` o `{ }` para
cambiar el orden (deben cerrarse con su pareja).

**También puedes escribir:** `~` `&` `|` `->` `<->` `XOR` directamente en la expresión.
""")
    with g2:
        with st.expander("⚖️ Leyes que usa el procedimiento"):
            st.markdown(
                "Condicional, Bicondicional, XOR, Doble negación, De Morgan, Identidad, Dominación, "
                "Complemento, Idempotencia, Absorción (y generalizada), Distributiva (factor común), "
                "Asociativa y Conmutativa."
            )

    st.markdown("""
<div style='text-align: center; color: gray; font-size: 0.9em; margin-top:1rem'>
🎓 <strong>Estructuras Discretas</strong> - Ingeniería en Software · 💻 Python y Streamlit
</div>
""", unsafe_allow_html=True)


if __name__ == "__main__":
    main()




