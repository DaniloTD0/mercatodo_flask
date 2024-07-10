from flask import Flask, render_template, request, redirect, url_for, session, flash
import database as db  # Aquí importamos la conexión como 'db'
import mysql.connector

app = Flask(__name__)
app.secret_key = 'supersecretkey'

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        rol = request.form['rol']

        cursor = db.db.cursor(dictionary=True)  # Utilizamos db.db para obtener la conexión

        if rol == 'empleado':
            cursor.execute('SELECT * FROM usuarios WHERE Nombre = %s AND cedula = %s', (username, password))
        else:
            cursor.execute('SELECT * FROM admin WHERE nombre = %s AND cc = %s', (username, password))

        user = cursor.fetchone()

        if user:
            session['id_usuario'] = user['ID_usuario'] if rol == 'empleado' else user['cc']
            if rol == 'empleado':
                return redirect(url_for('ventas'))
            else:
                return redirect(url_for('compras'))

        flash('Invalid username or password')
        return redirect(url_for('index'))

@app.route('/ventas', methods=['GET', 'POST'])
def ventas():
    if 'id_usuario' not in session:
        return redirect(url_for('index'))

    cursor = db.db.cursor(dictionary=True)

    categorias = []
    productos = []
    selected_categoria_id = request.form.get('categoria_id', None)
    search_query = request.form.get('search_query', '')

    venta_id = session.get('venta_id')

    if request.method == 'POST':
        if 'id_producto' in request.form and 'cantidad' in request.form:
            id_producto = request.form['id_producto']
            cantidad = int(request.form['cantidad'])

            cursor.execute('SELECT * FROM producto WHERE ID_producto = %s', (id_producto,))
            producto = cursor.fetchone()

            if producto and producto['stock'] >= cantidad:
                try:
                    if not venta_id:
                        # Crear una nueva venta
                        cursor.execute('INSERT INTO ventas (fecha_venta, ID_usuario) VALUES (NOW(), %s)', (session['id_usuario'],))
                        db.db.commit()
                        venta_id = cursor.lastrowid
                        session['venta_id'] = venta_id

                    # Insertar detalle de venta
                    cursor.execute('INSERT INTO detalle_ventas (ID_venta, ID_producto, cantidad, valor_venta_producto) VALUES (%s, %s, %s, %s)', 
                                   (venta_id, id_producto, cantidad, producto['valor_producto']))
                    db.db.commit()

                    # Actualizar total de la venta
                    cursor.execute('SELECT SUM(cantidad * valor_venta_producto) AS total FROM detalle_ventas WHERE ID_venta = %s', (venta_id,))
                    total_venta = cursor.fetchone()['total'] or 0
                    cursor.execute('UPDATE ventas SET total = %s WHERE ID_venta = %s', (total_venta, venta_id))
                    db.db.commit()

                    # Actualizar stock del producto
                    new_stock = producto['stock'] - cantidad
                    cursor.execute('UPDATE producto SET stock = %s WHERE ID_producto = %s', (new_stock, id_producto))
                    db.db.commit()

                    flash('Producto agregado a la venta')
                except mysql.connector.Error as err:
                    flash(f"Error al agregar producto a la venta: {err}")
            else:
                flash('No hay suficiente stock')
        else:
            flash('error')

    # Obtener categorías y productos para mostrar en la página
    cursor.execute('SELECT * FROM categoria_producto')
    categorias = cursor.fetchall()

    query = 'SELECT * FROM producto'
    if selected_categoria_id:
        query += ' WHERE ID_categoria_producto = %s'
        cursor.execute(query, (selected_categoria_id,))
    elif search_query:
        query += ' WHERE nombre_producto LIKE %s'
        cursor.execute(query, ('%' + search_query + '%',))
    else:
        cursor.execute(query)

    productos = cursor.fetchall()

    # Obtener detalles de la venta actual
    detalles_venta = []
    total_venta = 0
    if venta_id:
        cursor.execute('SELECT dv.ID_detalle_venta, dv.ID_venta, p.nombre_producto, dv.cantidad, dv.valor_venta_producto '
                       'FROM detalle_ventas dv '
                       'JOIN producto p ON dv.ID_producto = p.ID_producto '
                       'WHERE dv.ID_venta = %s', (venta_id,))
        detalles_venta = cursor.fetchall()

        cursor.execute('SELECT total FROM ventas WHERE ID_venta = %s', (venta_id,))
        total_venta = cursor.fetchone()['total'] or 0

    cursor.close()

    return render_template('ventas.html', categorias=categorias, productos=productos, detalles_venta=detalles_venta, selected_categoria_id=selected_categoria_id, search_query=search_query, total_venta=total_venta)

@app.route('/ventas/editar/<int:id>', methods=['POST'])
def editar_producto(id):
    if request.method == 'POST':
        nueva_cantidad = int(request.form['cantidad'])

        cursor = db.db.cursor(dictionary=True)
        cursor.execute('SELECT * FROM detalle_ventas WHERE ID_detalle_venta = %s', (id,))
        detalle_venta = cursor.fetchone()

        if detalle_venta:
            id_producto = detalle_venta['ID_producto']
            cursor.execute('SELECT * FROM producto WHERE ID_producto = %s', (id_producto,))
            producto = cursor.fetchone()

            if producto:
                diferencia = nueva_cantidad - detalle_venta['cantidad']
                nuevo_stock = producto['stock'] - diferencia
                cursor.execute('UPDATE producto SET stock = %s WHERE ID_producto = %s', (nuevo_stock, id_producto))
                db.db.commit()

                cursor.execute('UPDATE detalle_ventas SET cantidad = %s WHERE ID_detalle_venta = %s', (nueva_cantidad, id))
                db.db.commit()

                # Actualizar total de la venta
                cursor.execute('SELECT SUM(cantidad * valor_venta_producto) AS total FROM detalle_ventas WHERE ID_venta = %s', (detalle_venta['ID_venta'],))
                total_venta = cursor.fetchone()['total'] or 0
                cursor.execute('UPDATE ventas SET total = %s WHERE ID_venta = %s', (total_venta, detalle_venta['ID_venta']))
                db.db.commit()

                flash('Producto editado correctamente')

    return redirect(url_for('ventas'))

@app.route('/ventas/eliminar/<int:id>', methods=['POST'])
def eliminar_producto(id):
    cursor = db.db.cursor(dictionary=True)
    cursor.execute('SELECT * FROM detalle_ventas WHERE ID_detalle_venta = %s', (id,))
    detalle_venta = cursor.fetchone()

    if detalle_venta:
        id_producto = detalle_venta['ID_producto']
        cantidad = detalle_venta['cantidad']
        cursor.execute('SELECT * FROM producto WHERE ID_producto = %s', (id_producto,))
        producto = cursor.fetchone()

        if producto:
            nuevo_stock = producto['stock'] + cantidad
            cursor.execute('UPDATE producto SET stock = %s WHERE ID_producto = %s', (nuevo_stock, id_producto))
            db.db.commit()

            cursor.execute('DELETE FROM detalle_ventas WHERE ID_detalle_venta = %s', (id,))
            db.db.commit()

            # Actualizar total de la venta
            cursor.execute('SELECT SUM(cantidad * valor_venta_producto) AS total FROM detalle_ventas WHERE ID_venta = %s', (detalle_venta['ID_venta'],))
            total_venta = cursor.fetchone()['total'] or 0
            cursor.execute('UPDATE ventas SET total = %s WHERE ID_venta = %s', (total_venta, detalle_venta['ID_venta']))
            db.db.commit()

            flash('Producto eliminado correctamente')

    return redirect(url_for('ventas'))

@app.route('/ventas/cancelar', methods=['POST'])
def cancelar_venta():
    venta_id = session.get('venta_id', None)

    if venta_id:
        cursor = db.db.cursor(dictionary=True)
        cursor.execute('SELECT * FROM detalle_ventas WHERE ID_venta = %s', (venta_id,))
        detalles_venta = cursor.fetchall()

        for detalle in detalles_venta:
            id_producto = detalle['ID_producto']
            cantidad = detalle['cantidad']
            cursor.execute('SELECT * FROM producto WHERE ID_producto = %s', (id_producto,))
            producto = cursor.fetchone()

            if producto:
                nuevo_stock = producto['stock'] + cantidad
                cursor.execute('UPDATE producto SET stock = %s WHERE ID_producto = %s', (nuevo_stock, id_producto))
                db.db.commit()

        cursor.execute('DELETE FROM detalle_ventas WHERE ID_venta = %s', (venta_id,))
        cursor.execute('DELETE FROM ventas WHERE ID_venta = %s', (venta_id,))
        db.db.commit()

        session.pop('venta_id', None)

        flash('Venta cancelada correctamente')

    return redirect(url_for('ventas'))

@app.route('/ventas/finalizar', methods=['POST'])
def finalizar_venta():
    venta_id = session.get('venta_id', None)

    if venta_id:
        cursor = db.db.cursor(dictionary=True)
        
        # Asegurarse de que el total se ha calculado y actualizado correctamente
        cursor.execute('SELECT SUM(cantidad * valor_venta_producto) AS total FROM detalle_ventas WHERE ID_venta = %s', (venta_id,))
        total_venta = cursor.fetchone()['total'] or 0
        cursor.execute('UPDATE ventas SET total = %s WHERE ID_venta = %s', (total_venta, venta_id))
        db.db.commit()

        session.pop('venta_id', None)

        flash('Venta finalizada correctamente')

    return redirect(url_for('ventas'))

@app.route('/compras', methods=['GET', 'POST'])
def compras():
    if 'id_usuario' not in session:
        return redirect(url_for('index'))

    cursor = db.db.cursor(dictionary=True)

    proveedores = []
    productos = []
    selected_proveedor_id = request.form.get('proveedor_id', None)  # Corregido: 'proveedor_id' a 'categoria_id'
    search_query = request.form.get('search_query', '')

    compra_id = session.get('compra_id')

    if request.method == 'POST':
        if 'id_producto' in request.form and 'cantidad' in request.form:

            id_producto = request.form.get('id_producto')
            cantidad = int(request.form.get('cantidad', 0))  # Asegúrate de manejar adecuadamente valores nulos

            cursor.execute('SELECT * FROM producto WHERE ID_producto = %s', (id_producto,))
            producto = cursor.fetchone()
                
            if producto and producto['stock'] >= 0:
                try:
                    if not compra_id:
                        # Crear una nueva compra
                        cursor.execute('INSERT INTO compras (fecha_compra) VALUES (NOW())')
                        db.db.commit()
                        compra_id = cursor.lastrowid
                        session['compra_id'] = compra_id

                    # Insertar detalle de compra
                    cursor.execute('INSERT INTO detalle_compra (ID_compra, ID_proveedor, ID_producto, cantidad, valor_compra_producto) VALUES (%s, %s, %s, %s, %s)', 
                                (compra_id,  id_producto, cantidad, producto['valor_producto']))
                    db.db.commit()

                    # Actualizar total de la compra
                    cursor.execute('SELECT SUM(cantidad * valor_compra_producto) AS total FROM detalle_compra WHERE ID_compra = %s', (compra_id,))
                    total_compra = cursor.fetchone()['total'] or 0
                    cursor.execute('UPDATE compras SET total = %s WHERE ID_compra = %s', (total_compra, compra_id))
                    db.db.commit()
                    

                    # Actualizar stock del producto
                    new_stock = producto['stock'] + cantidad
                    cursor.execute('UPDATE producto SET stock = %s WHERE ID_producto = %s', (new_stock, id_producto))
                    db.db.commit()

                    flash('Producto agregado a la compra')

                    # Recargar los detalles de la compra después de la inserción
                    # return redirect(url_for('compras'))  # Redirigir para actualizar la página
                except mysql.connector.Error as err:
                    flash(f"Error al agregar producto a la compra: {err}")
            else:
                flash('#')
        else:
            flash('Faltan datos necesarios para agregar el producto a la compra')

    # Obtener proveedores y productos para mostrar en la página
    cursor.execute('SELECT * FROM proveedores')
    proveedores = cursor.fetchall()

    query = 'SELECT * FROM producto'
    if selected_proveedor_id:
        query += ' WHERE ID_proveedor = %s'
        cursor.execute(query, (selected_proveedor_id,))
    elif search_query:
        query += ' WHERE nombre_producto LIKE %s'
        cursor.execute(query, ('%' + search_query + '%',))
    else:
        cursor.execute(query)

    productos = cursor.fetchall()

    # Obtener detalles de la compra actual
    detalles_compra = []
    total_compra = 0
    if compra_id:
        cursor.execute('SELECT dc.ID_detalle_compra, dc.ID_compra, p.nombre_producto, dc.cantidad, dc.valor_compra_producto '
                       'FROM detalle_compra dc '
                       'JOIN producto p ON dc.ID_producto = p.ID_producto '
                       
                       'WHERE dc.ID_compra = %s', (compra_id,))
        detalles_compra = cursor.fetchall()

        cursor.execute('SELECT valor_compra_producto FROM detalle_compra WHERE ID_compra = %s', (compra_id,))
        total_compra = cursor.fetchone()['total'] or 0

    cursor.close()

    return render_template('compras.html', proveedores=proveedores, productos=productos, detalles_compra=detalles_compra, selected_proveedor_id=selected_proveedor_id, search_query=search_query, total_compra=total_compra)

@app.route('/compras/editar/<int:id>', methods=['POST'])
def editar_producto_compra(id):
    if request.method == 'POST':
        nueva_cantidad = int(request.form['cantidad'])

        cursor = db.db.cursor(dictionary=True)
        cursor.execute('SELECT * FROM detalle_compra WHERE ID_detalle_compra = %s', (id,))
        detalle_compra = cursor.fetchone()

        if detalle_compra:
            id_producto = detalle_compra['ID_producto']
            cursor.execute('SELECT * FROM producto WHERE ID_producto = %s', (id_producto,))
            producto = cursor.fetchone()

            if producto:
                diferencia = nueva_cantidad - detalle_compra['cantidad']
                nuevo_stock = producto['stock'] + diferencia  # Corregido: Actualizar el stock sumando la diferencia
                cursor.execute('UPDATE producto SET stock = %s WHERE ID_producto = %s', (nuevo_stock, id_producto))
                db.db.commit()

                cursor.execute('UPDATE detalle_compra SET cantidad = %s WHERE ID_detalle_compra = %s', (nueva_cantidad, id))
                db.db.commit()

                # Actualizar total de la compra
                cursor.execute('SELECT SUM(cantidad * valor_compra_producto) AS total FROM detalle_compra WHERE ID_compra = %s', (detalle_compra['ID_compra'],))
                total_compra = cursor.fetchone()['total'] or 0
                cursor.execute('UPDATE compras SET total = %s WHERE ID_compra = %s', (total_compra, detalle_compra['ID_compra']))
                db.db.commit()

                flash('Producto editado correctamente')

    return redirect(url_for('compras'))

@app.route('/compras/eliminar/<int:id>', methods=['POST'])
def eliminar_producto_compra(id):
    cursor = db.db.cursor(dictionary=True)
    cursor.execute('SELECT * FROM detalle_compra WHERE ID_detalle_compra = %s', (id,))
    detalle_compra = cursor.fetchone()

    if detalle_compra:
        id_producto = detalle_compra['ID_producto']
        cantidad = detalle_compra['cantidad']
        cursor.execute('SELECT * FROM producto WHERE ID_producto = %s', (id_producto,))
        producto = cursor.fetchone()

        if producto:
            nuevo_stock = producto['stock'] + cantidad
            cursor.execute('UPDATE producto SET stock = %s WHERE ID_producto = %s', (nuevo_stock, id_producto))
            db.db.commit()

            cursor.execute('DELETE FROM detalle_compra WHERE ID_detalle_compra = %s', (id,))
            db.db.commit()

            # Actualizar total de la compra
            cursor.execute('SELECT SUM(cantidad * valor_compra_producto) AS total FROM detalle_compra WHERE ID_compra = %s', (detalle_compra['ID_compra'],))
            total_compra = cursor.fetchone()['total'] or 0
            cursor.execute('UPDATE compras SET total = %s WHERE ID_compra = %s', (total_compra, detalle_compra['ID_compra']))
            db.db.commit()

            flash('Producto eliminado correctamente')

    return redirect(url_for('compras'))

@app.route('/compras/cancelar', methods=['POST'])
def cancelar_compra():
    compra_id = session.get('compra_id', None)

    if compra_id:
        cursor = db.db.cursor(dictionary=True)
        cursor.execute('SELECT * FROM detalle_compra WHERE ID_compra = %s', (compra_id,))
        detalles_compra = cursor.fetchall()

        for detalle in detalles_compra:
            id_producto = detalle['ID_producto']
            cantidad = detalle['cantidad']
            cursor.execute('SELECT * FROM producto WHERE ID_producto = %s', (id_producto,))
            producto = cursor.fetchone()

            if producto:
                nuevo_stock = producto['stock'] + cantidad
                cursor.execute('UPDATE producto SET stock = %s WHERE ID_producto = %s', (nuevo_stock, id_producto))
                db.db.commit()

        cursor.execute('DELETE FROM detalle_compra WHERE ID_compra = %s', (compra_id,))
        cursor.execute('DELETE FROM compras WHERE ID_compra = %s', (compra_id,))
        db.db.commit()

        session.pop('compra_id', None)

        flash('Compra cancelada correctamente')

    return redirect(url_for('compras'))

@app.route('/compras/finalizar', methods=['POST'])
def finalizar_compra():
    compra_id = session.get('compra_id', None)

    if compra_id:
        cursor = db.db.cursor(dictionary=True)
        
        # Asegurarse de que el total se ha calculado y actualizado correctamente
        cursor.execute('SELECT SUM(cantidad * valor_compra_producto) AS total FROM detalle_compra WHERE ID_compra = %s', (compra_id,))
        total_compra = cursor.fetchone()['total'] or 0
        cursor.execute('UPDATE compras SET total = %s WHERE ID_compra = %s', (total_compra, compra_id))
        db.db.commit()

        session.pop('compra_id', None)

        flash('Compra finalizada correctamente')

    return redirect(url_for('compras'))


if __name__ == '__main__':
    app.run(debug=True)