from flask import Flask, redirect, render_template, request, flash
from werkzeug.utils import secure_filename
import os


import functions
from scipy.optimize import fmin_l_bfgs_b
import time
from keras import backend as K
import numpy as np
import json
import time

STYLE_FOLDER = './static/img/style'
CONTENT_FOLDER = './static/img/content'
TRANSFER_FOLDER = './static/img/transfer'
ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg'])

app = Flask(__name__)
app.secret_key = "91d44dbb7d032001ddd4335cd7995fe4851bc8fcf5ec4e50"
app.config['STYLE_FOLDER'] = STYLE_FOLDER
app.config['CONTENT_FOLDER'] = CONTENT_FOLDER
app.config['TRANSFER_FOLDER'] = TRANSFER_FOLDER
app.debug = True

class Variables():
	def __init__(self):
		self.width = 0
		self.height = 0
		self.f_outputs = None

variables = Variables()

class Evaluator(object):

	def __init__(self):
		self.loss_value = None
		self.grads_values = None

	def loss(self, x):
		assert self.loss_value is None
		loss_value, grad_values = functions.eval_loss_and_grads(x, variables.width, variables.height, variables.f_outputs)
		self.loss_value = loss_value
		self.grad_values = grad_values
		return self.loss_value

	def grads(self, x):
		assert self.loss_value is not None
		grad_values = np.copy(self.grad_values)
		self.loss_value = None
		self.grad_values = None
		return grad_values

def allowed_file(filename):
	return '.' in filename and \
		filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# def print_all(x):
# 	print(x)
# 	print(type(x))
# 	try:
# 		print(x.shape)
# 	except:
# 		print("Cant print shape")

def style_transfer(content_image_path, style_image_path, result_prefix='transfer_', iterations=1, content_weight=0.025, style_weight = 1.0, total_variation_weight = 1):
	# dimensions of the generated picture.
	evaluator = Evaluator()
	content_weight = float(content_weight)
	style_weight = float(style_weight)
	result_prefix = TRANSFER_FOLDER + "/" + str(int(time.time()))+ "_" + result_prefix
	variables.width, variables.height = functions.load_image(content_image_path).size
	content_image = K.variable(functions.preprocess_image(content_image_path, variables.width, variables.height))
	style_reference_image = K.variable(functions.preprocess_image(style_image_path,variables.width, variables.height))
	img_nrows, img_ncols = functions.calc_rowsandcols(variables.width,variables.height)
	if K.image_data_format() == 'channels_first':
		combination_image = K.placeholder((1, 3, img_nrows, img_ncols))
	else:
		combination_image = K.placeholder((1, img_nrows, img_ncols, 3))
	# print_all(content_image)
	# print_all(style_reference_image)
	# print_all(combination_image)
	input_tensor = K.concatenate([content_image,
							  style_reference_image,
							  combination_image], axis=0)
	# print_all(input_tensor)
	# exit(0)
	model = functions.customVGG16(input_tensor)
	outputs_dict = dict([(layer.name, layer.output) for layer in model.layers])
	loss = K.variable(0.)
	layer_features = outputs_dict['conv2d_12']
	content_image_features = layer_features[0, :, :, :]
	combination_features = layer_features[2, :, :, :]
	loss += content_weight * functions.content_loss(content_image_features,
									  combination_features)
	feature_layers = ['conv2d_1', 'conv2d_3',
				  'conv2d_5', 'conv2d_8',
				  'conv2d_11']
	for layer_name in feature_layers:
		layer_features = outputs_dict[layer_name]
		style_reference_features = layer_features[1, :, :, :]
		combination_features = layer_features[2, :, :, :]
		sl = functions.style_loss(style_reference_features, combination_features,variables.width,variables.height)
		loss += (style_weight / len(feature_layers)) * sl
	loss += total_variation_weight * functions.total_variation_loss(combination_image,variables.width,variables.height)
	grads = K.gradients(loss, combination_image)
	outputs = [loss]
	if isinstance(grads, (list, tuple)):
		outputs += grads
	else:
		outputs.append(grads)

	variables.f_outputs = K.function([combination_image], outputs)
	x = functions.preprocess_image(content_image_path,variables.width,variables.height)
	start_time = time.time()
	for i in range(int(iterations)):
		print('Start of iteration', i)
		iter_start_time = time.time()
		x, min_val, info = fmin_l_bfgs_b(evaluator.loss, x.flatten(),
										 fprime=evaluator.grads, maxfun=20, maxiter=1)
		print('Current loss value:', min_val)
		end_time = time.time()
		print('Iteration %d completed in %ds' % (i, end_time - iter_start_time))
		# return [min_val,fname,i,end_time-start_time]

	# save current generated image
	img = functions.deprocess_image(x.copy(),img_nrows, img_ncols)
	fname = result_prefix + 'at_iteration_%d.png' % i
	functions.save_image(img,fname)
	values = [iterations,str(round(min_val,2)),str(round(end_time-start_time,2)),fname]
	return values
		

@app.route("/")
def index():
	return render_template("index.html")

@app.route('/uploadajax/', methods=['POST','GET'])
def uploadajax():
	if 'file' not in request.files:
		return('No file part')
	
	file = request.files['file']

	if file.filename == '':
		return('No selected file')

	if request.method == 'POST':
		if 'file' not in request.files or 'afile' not in request.files:
			flash('No file part')
		styleimage = request.files['afile']
		contentimage = request.files['file']
		iterations = request.form['iterations']
		style_weight = request.form['sweight']
		content_weight = request.form['cweight']
		if iterations == "":
			iterations = 1
		if style_weight == "":
			style_weight = 1.0
		if content_weight == "":
			content_weight = 0.025
		if styleimage.filename == '' or contentimage.filename == '':
			flash('No selected file')
		if styleimage and contentimage and allowed_file(styleimage.filename) and allowed_file(contentimage.filename):
			styleimagename = secure_filename(styleimage.filename)
			contentimagename = secure_filename(contentimage.filename)
			styleimage_path = os.path.join(app.config['STYLE_FOLDER'], styleimagename)
			contentimage_path = os.path.join(app.config['CONTENT_FOLDER'], contentimagename)
			styleimage.save(styleimage_path)
			contentimage.save(contentimage_path)

		values = style_transfer(contentimage_path, styleimage_path, iterations=iterations, content_weight=content_weight, style_weight = style_weight)
		return(json.dumps(values))


if __name__ == "__main__":
	app.run(host='0.0.0.0', port=5000)