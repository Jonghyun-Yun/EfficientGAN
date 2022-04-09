#from keras.models import Sequential, Model
#from keras.layers import Input, Dense, LeakyReLU, Concatenate, Dropout
#from keras.layers.normalization import BatchNormalization
#from keras.optimizers import Adam

import tensorflow as tf
#from tensorflow.keras.models import Sequential
from tensorflow.python.keras.layers import Input, Dense, LeakyReLU, Concatenate, Dropout
from tensorflow.python.keras.models import Model
from tensorflow.keras.layers import Input, Dense, LeakyReLU, Concatenate, Dropout
#from tensorflow.keras import Model
#from tensorflow.keras.optimizers import Adam
from sklearn.preprocessing import minmax_scale
import numpy as np

class EfficientGAN(object):
    def __init__(self, input_dim=0, latent_dim=32):
        self.input_dim = int(input_dim)
        self.latent_dim = int(latent_dim)
      
    #Train model
    def fit(self, X_train, epochs=50, batch_size=64, loss=tf.keras.losses.BinaryCrossentropy(),
            optimizer=tf.keras.optimizers.Adam(learning_rate=1e-5, beta_1=0.5), test=tuple(), early_stop_num=50, verbose=1):
        
        #Convert training-data to numpy format
        X_train = np.array(X_train)
        
        #If "input_dim" is not greater than 1, it is set to the number of features in the training-data
        if not self.input_dim >= 1: self.input_dim = X_train.shape[1]
        
        #Define model for Discriminator
        self.dis = self.get_discriminator()
        self.dis.compile(loss=loss, optimizer=optimizer)
      
        #Define model to train Encoder
        self.enc = self.get_encoder()
        x = Input(shape=(self.input_dim,))
        z_gen = self.enc(x)
        valid = self.dis([x, z_gen])
        enc_dis = Model(inputs=x, outputs=valid, name='enc_to_dis')
        enc_dis.compile(loss=loss, optimizer=optimizer) 
        
        #Define model to train Generator
        self.gen = self.get_generator()        
        z = Input(shape=(self.latent_dim,))
        x_gen = self.gen(z)
        valid = self.dis([x_gen, z])
        gen_dis = Model(inputs=z, outputs=valid, name='gen_to_dis')
        gen_dis.compile(loss=loss, optimizer=optimizer)          
        
        #Training
        min_val_loss = float('inf')
        stop_count = 0
        for i in range(epochs):    
            #Unfreeze Discriminator
            self.dis.trainable = True
                
            #From the training data, randomly choice half of the "batch_size" as "real_data"
            idx = np.random.randint(0, X_train.shape[0], batch_size//2)
            real_data = X_train[idx]
    
            #Generates noise and get the data generated by that noise
            noise = np.random.normal(0, 1, (len(idx), self.latent_dim))
            gen_data = self.gen.predict(noise)
    
            #Get noise predicted from "real_data"
            enc_noise = self.enc.predict(real_data)
               
            #Train Discriminator
            d_enc_loss = self.dis.train_on_batch([real_data, enc_noise], np.ones((len(real_data), 1)))
            d_gen_loss = self.dis.train_on_batch([gen_data, noise], np.zeros((len(gen_data), 1)))
            d_loss = d_enc_loss + d_gen_loss
    
            #Freeze Discriminator to train Encoder and Generator
            self.dis.trainable = False
    
            #Train Encoder
            e_loss = enc_dis.train_on_batch(real_data, np.zeros((len(real_data), 1)))
        
            #Train Generator
            g_loss = gen_dis.train_on_batch(noise, np.ones((len(noise), 1)))
                 
            #Calculate test loss
            if len(test)>0:
                #Get testing-data
                X_test = test[0]
                y_true = test[1]
                
                #Predict testing-data
                proba = self.predict(X_test)
                proba = minmax_scale(proba)
                
                #As "val_loss", calculate binary cross entropy
                val_loss = tf.keras.losses.binary_crossentropy(y_true, proba).numpy()
                
                #If "val_loss" is less than "min_val_loss"
                if min_val_loss > val_loss:                                        
                    min_val_loss = val_loss #Update "min_val_loss" to "val_loss"
                    stop_count = 0 #Change "stop_count" to 0
                #If "stop_count" is equal or more than "early_stop_num", training is end
                elif stop_count >= early_stop_num:
                    break
                #Else, "stop_count" is added 1
                else:
                    stop_count += 1               
                    
            #Display learning progress
            if verbose==1 and i%10==0:
                if len(test)==0: print(f'epoch{i}-> d_loss:{d_loss}  e_loss:{e_loss}  g_loss:{g_loss}')
                else: print(f'epoch{i}-> d_loss:{d_loss}  e_loss:{e_loss}  g_loss:{g_loss}  val_loss:{val_loss}')
    
    #Test model
    def predict(self, X_test, weight=0.9, degree=1):
        
        #Convert testing-data to numpy format
        X_test = np.array(X_test)
        
        #Get noise predicted from testing-data
        z_gen = self.enc.predict(X_test)
        
        #Get the data generated by that noise predicted from testing-data
        reconstructs = self.gen.predict(z_gen)
                
        #As "gen_score", calculation of the norm of difference between testing-data and generated data for each features
        #The more different the testing-data is from the training-data, the higher the score (=anomality)        
        '''
            If testing-data is similar to the training-data,
            the data generated by a well-trained Encoder and Genrator can reproduce the testing-data.
        '''        
        delta = X_test - reconstructs
        gen_score = tf.norm(delta, ord=degree, axis=1).numpy()
        
        #Inference of Encoder's input and output in the Discriminator
        l_encoder = self.dis.predict([X_test, z_gen])
        
        #As "dis_score", calculate binary cross entropy from the results of the inference
        #The more different the testing-data is from the training-data, the higher the score (=anomality)        
        '''
            If testing-data is similar to the training-data,
            result of inference of testing-data and the noise encoded from testing-data in the Discriminator approaches 1.
        '''
        dis_score = tf.keras.losses.binary_crossentropy(np.ones((len(X_test), 1)), l_encoder).numpy()
    
        #Return anomality calculated "gen_score" and "dis_score"
        return weight*gen_score + (1-weight)*dis_score      
        
    ##Encoder
    def get_encoder(self, initializer=tf.keras.initializers.GlorotUniform()):
        inputs = Input(shape=(self.input_dim,), name='input')
        net = inputs
        net = Dense(64, activation=LeakyReLU(alpha=0.1), kernel_initializer=initializer,
                    name='layer_1')(net)
        outputs = Dense(self.latent_dim, activation='linear', kernel_initializer=initializer,
                        name='output')(net)
    
        return Model(inputs=inputs, outputs=outputs, name='Encoder')
    
    ##Generator
    def get_generator(self, initializer=tf.keras.initializers.GlorotUniform()):
        inputs = Input(shape=(self.latent_dim,), name='input')
        net = inputs
        net = Dense(64, activation='relu', kernel_initializer=initializer,
                    name='layer_1')(net)
        net = Dense(128, activation='relu', kernel_initializer=initializer,
                    name='layer_2')(net)
        outputs = Dense(self.input_dim, activation='linear', kernel_initializer=initializer,
                        name='output')(net)
    
        return Model(inputs=inputs, outputs=outputs, name='Generator')
    
    ##Discriminator
    def get_discriminator(self, initializer=tf.keras.initializers.GlorotUniform()):
        #D(x)
        inputs1 = Input(shape=(self.input_dim,), name='real')
        net = inputs1
        net = Dense(128, activation=LeakyReLU(alpha=0.1), kernel_initializer=initializer,
                    name='layer_1')(net)
        dx = Dropout(.2)(net)
    
        #D(z)
        inputs2 = Input(shape=(self.latent_dim,), name='noise')
        net = inputs2
        net = Dense(128, activation=LeakyReLU(alpha=0.1), kernel_initializer=initializer,
                    name='layer_2')(net)
        dz = Dropout(.2)(net)
    
        #concat D(x) and D(z)
        conet = Concatenate(axis=1)([dx,dz])
    
        #D(x,z)
        conet = Dense(128, activation=LeakyReLU(alpha=0.1), kernel_initializer=initializer,
                      name='layer_3')(conet)
        conet = Dropout(.2)(conet)
        outputs = Dense(1, activation='sigmoid', kernel_initializer=initializer,
                        name='output')(conet)

        return Model(inputs=[inputs1,inputs2], outputs=outputs, name='Discriminator')

#for debug    
def run(X_train, X_test, y_true):
    model = EfficientGAN()
    model.fit(X_train, test=(X_test,y_true))
    proba = model.predict(X_test)
    
from sklearn.datasets import load_iris
if __name__ == '__main__':    
    iris = load_iris()   
    run(iris['data'], iris['data'], iris['target'])
    