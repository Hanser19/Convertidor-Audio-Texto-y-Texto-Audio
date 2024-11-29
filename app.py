from flask import Flask, render_template, request, send_file, jsonify
from werkzeug.utils import secure_filename
import os
from pydub import AudioSegment
import speech_recognition as sr
from gtts import gTTS
from cryptography.fernet import Fernet
from pydub.utils import make_chunks

app = Flask(__name__)

# Generar una clave para encriptación y desencriptación
key = Fernet.generate_key()
cipher_suite = Fernet(key)

# Configuración
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'ogg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Función para verificar formatos permitidos
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Función para encriptar el archivo de audio
def encrypt_audio(filepath):
    with open(filepath, 'rb') as file:
        audio_data = file.read()
    encrypted_audio = cipher_suite.encrypt(audio_data)
    
    encrypted_filepath = filepath + '.enc'
    with open(encrypted_filepath, 'wb') as encrypted_file:
        encrypted_file.write(encrypted_audio)
    
    return encrypted_filepath

# Función para desencriptar el archivo de audio
def decrypt_audio(filepath):
    with open(filepath, 'rb') as encrypted_file:
        encrypted_audio = encrypted_file.read()
    decrypted_audio = cipher_suite.decrypt(encrypted_audio)
    
    decrypted_filepath = filepath.replace('.enc', '_decrypted.wav')
    with open(decrypted_filepath, 'wb') as decrypted_file:
        decrypted_file.write(decrypted_audio)
    
    return decrypted_filepath

# Función para encriptar la transcripción
def encrypt_transcription(transcription):
    encrypted_text = cipher_suite.encrypt(transcription.encode())
    return encrypted_text

# Transcripción de audio largo dividiéndolo en fragmentos
def transcribe_large_audio(filepath, chunk_length_ms=30000):  # 30 segundos
    recognizer = sr.Recognizer()
    audio = AudioSegment.from_file(filepath).set_frame_rate(16000).set_channels(1)  # Reducir calidad
    chunks = make_chunks(audio, chunk_length_ms)
    transcription = []

    for i, chunk in enumerate(chunks):
        chunk_path = f"{filepath}_chunk{i}.wav"
        chunk.export(chunk_path, format="wav")  # Guardar cada fragmento como archivo .wav

        with sr.AudioFile(chunk_path) as source:
            try:
                audio_data = recognizer.record(source)
                text = recognizer.recognize_google(audio_data, language='es-ES')
                transcription.append(text)
            except sr.UnknownValueError:
                transcription.append("[Ininteligible]")
            except sr.RequestError:
                transcription.append("[Error del servicio]")

    return " ".join(transcription)

# Ruta principal
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/convert-audio', methods=['POST'])
def convert_audio():
    if 'audio' not in request.files:
        return jsonify({'error': 'No se encontró el archivo de audio.'}), 400

    audio_file = request.files['audio']
    filepath = os.path.join('uploads', audio_file.filename)
    audio_file.save(filepath)

    # Verificar si el archivo es una grabación web (sin encriptar)
    if "recorded" in request.form:  # Si es una grabación desde la web
        try:
            # Procesar el archivo de audio sin encriptación
            text = transcribe_large_audio(filepath)
            return jsonify({'transcription': text})  # Devolver la transcripción sin encriptar
        except Exception as e:
            return jsonify({'error': f'Error al procesar el audio: {str(e)}'}), 500
    else:
        # Si no es una grabación web, encriptar el archivo de audio para almacenamiento
        encrypted_filepath = encrypt_audio(filepath)

        # Desencriptar el archivo antes de la transcripción
        decrypted_filepath = decrypt_audio(encrypted_filepath)

        try:
            text = transcribe_large_audio(decrypted_filepath)
            return jsonify({'transcription': text})  # Devolver la transcripción sin encriptar
        except Exception as e:
            return jsonify({'error': f'Error al procesar el audio: {str(e)}'}), 500
        

@app.route('/audio-to-text', methods=['POST'])
def audio_to_text():
    if 'audio' not in request.files:
        return jsonify({'error': 'No se proporcionó un archivo de audio'}), 400

    file = request.files['audio']
    if file.filename == '':
        return jsonify({'error': 'No se seleccionó ningún archivo'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': f'Formato no soportado. Formatos permitidos: {", ".join(ALLOWED_EXTENSIONS)}'}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    try:
        # Transcribir el audio a texto
        text = transcribe_large_audio(filepath)
        
        # Encriptar la transcripción
        encrypted_transcription = encrypt_transcription(text)
        
        # Devolver la transcripción encriptada
        return jsonify({'transcription': encrypted_transcription.decode()})
    except Exception as e:
        return jsonify({'error': f'Error al procesar el audio: {str(e)}'}), 500

# Convertir texto a audio
@app.route('/text-to-audio', methods=['POST'])
def text_to_audio():
    data = request.json
    if not data or 'text' not in data:
        return jsonify({'error': 'Texto no proporcionado'}), 400

    text = data['text']
    try:
        tts = gTTS(text, lang='es')
        output_path = os.path.join(UPLOAD_FOLDER, 'output.mp3')
        tts.save(output_path)
        return send_file(output_path, as_attachment=True)
    except Exception as e:
        return jsonify({'error': f'Error al convertir texto a audio: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True)
