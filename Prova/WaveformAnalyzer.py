#Ora, tutto, ma più bokrh-friendly
import pandas as pd
from glob import glob 
import numpy as np
import re
from scipy import optimize
from scipy import special
from scipy import integrate
from scipy import stats
import matplotlib.pyplot as plt
from scipy.signal import butter,lfilter
from scipy.ndimage import gaussian_filter
from time import time
from bokeh.layouts import gridplot,column,row
from bokeh.plotting import figure, output_file, show,output_notebook
from bokeh.models import Slider,Button,Select,ColumnDataSource,Paragraph,TextInput,TextAreaInput,Label
from bokeh.io import curdoc
from io import StringIO
from DatabaseWriter import DatabaseWrite
from FakeWaveformReader import FakeWaveformReader
from WaveformReader import WaveformReader
from tqdm import tqdm 
from UsefulFunctions import UsefulFunctions as UF

dfit=pd.read_csv('Fitting_parameters.csv',index_col=0,delimiter=',',comment='#')
text_file=open('Default_text.txt','r')
p0_GB=[dfit['valore']['amplGB'],dfit['valore']['muGB'],dfit['valore']['sigma1GB'],dfit['valore']['sigma2GB'],dfit['valore']['baselineGB']]
p0_GS=[dfit['valore']['amplGS'],dfit['valore']['muGS'],dfit['valore']['sigmaGS'],dfit['valore']['skewnessGS'],dfit['valore']['baselineGS']]
p0_L=[dfit['valore']['muL'],dfit['valore']['sigmaL']]
p0_LG=[dfit['valore']['mulandLG'],dfit['valore']['mugaussLG'],dfit['valore']['sigmalandLG'],dfit['valore']['sigmagaussLG']]
Gain=dfit['valore']['gain']
div_noise=int([dfit['valore']['div']][0])
Default_text=text_file.read()
text_file.close()

#CALCOLO SISTEMATICO AMPIEZZE GRAFICI
#------------------------------------------------------------------------------------------------------------------------------

def Amplitude_dist(t,C,mode=0,step=20,nfiles=0):



  '''Computes the amplitudes of a set of waveforms, with 3 different methods.
    it accepts arguments:

      t (array): time at wich each measurement was taken
      
      C (array): value of each measurement
      
      mode=0 (int): method used to calculate amplitudes, it has values
          0: bifurcated Gaussian
          1: skewed Gaussian
          2: finds the minimum of each waveform without fitting it
      
      step=50 (int): frequency of samples used to calculate the fit 
      
      
  '''

  #inizializzazione array

  n=len(C)
  if nfiles!=0:
    right_files=np.random.randint(0,n,size=nfiles)
    C1=C[right_files]
    n=nfiles
  else:
    C1=np.copy(C)
    
  Amplitude=np.zeros(n)
  mu=np.zeros(n)
  baseline=np.zeros(n)
 
  #controllo errori
  if type(step)!=int:
    raise ValueError("L'argomento step deve essere un intero positivo")
  elif step<=0:
    raise ValueError("L'argomento step deve essere un intero positivo")

  #Selelzione modalità di fitting

  if mode==0:

    # modalità gaussiana biforcuta

    for i in tqdm(range(n)):
      pf=np.zeros(5)
      C1_sm=gaussian_filter(C1[i],30)
      try:
        pf,pcov=optimize.curve_fit(UF.gauss_asimm,t[i,::step],C1_sm[::step],p0=p0_GB)
      except:
        print('Errore a ',i)

      Amplitude[i]=pf[0]
      mu[i]=pf[1]
      baseline[i]=pf[4]

  elif mode==1:

    #modalità gaussiana skewed

      for i in tqdm(range(n)):

        pf=np.zeros(5)
        C1_sm=gaussian_filter(C1[i],40)

        #parte di fitting

        try:
          pf,pcov=optimize.curve_fit(UF.gauss_skew,t[i,::step],C1_sm[::step],p0=p0_GS)
        except:
          print('Errore a ',i)

        #parte di ricerca del minimo
        
        A=optimize.minimize(UF.gauss_skew,p0_GS[1],args=(pf[0],pf[1],pf[2],pf[3],pf[4]))

        Amplitude[i]=-A.fun+pf[4]
        mu[i]=A.x 
        baseline[i]=pf[4]

  elif mode==2:

    #modalità ricerca del minimo a partire dai dati filtrati

    for i in tqdm(range(n)):

      C1_sm=gaussian_filter(C1[i],40)
      Amplitude[i]=-np.min(C1_sm)
   
  return Amplitude,mu,baseline 

#METODI PER FITTARE GLI ISTOGRAMMI

def fit_hist(A,method=0):

  ''' Function used to fit the amplitudes histogram, with arguments:

      A: amplitudes of each waveform, output of "Amplitude_dist"
      method=0: function used in the fit, it accepts values
          0: Landau
          1: Landau+Gaussian
          2: Gaussian until a certain point, then Landau (not used)
   '''

  A0h,A0e_prov=np.histogram(A,bins=100,range=(0.1,100))
  A0e=0.5*(A0e_prov[1:]+A0e_prov[:-1])
  if method==0:
    nmoyal=sum(A0h[div_noise:])
    p0_L_def=[nmoyal,p0_L[0],p0_L[1]]
    pf,pcov=optimize.curve_fit(UF.just_moyal,A0e,A0h,p0=p0_L_def)
    
    A0hfit=UF.just_moyal(A0e,pf[0],pf[1],pf[2])
    chi2=(A0hfit-A0h)/A0h
  elif method==1:
    ngauss=sum(A0h[:div_noise])
    nmoyal=sum(A0h[7:])
    p0_LG_def=[ngauss,nmoyal,p0_LG[0],p0_LG[1],p0_LG[2],p0_LG[3]]
    pf,pcov=optimize.curve_fit(UF.moyalangauss,A0e,A0h,p0=p0_LG_def)
  
    
    A0hfit=UF.moyalangauss(A0e,pf[0],pf[1],pf[2],pf[3],pf[4],pf[5])
    chi2=(A0hfit-A0h)/A0h
  elif method==2:
    pf,pcov=optimize.curve_fit(UF.gaussanmoyal,A0e,A0h,p0=[5000.0 , 5, 17.0, 3.0, 10,0.1,5])
    A0hfit=UF.gaussanmoyal(A0e,pf[0],pf[1],pf[2],pf[3],pf[4],pf[5],pf[6])
  return A0h,A0e,A0hfit,pf,pcov


#METODI PER PLOTTARE I FIT
#---------------------------------------------------------------------------------------------------------------------------

def make_plot(title,source):
    '''Plots the histogram'''
    p = figure(title=title, tools='crosshair,pan,reset,save,wheel_zoom', background_fill_color="#fafafa")
    p.quad(top='hist',source=source, bottom=0, left='edges1', right='edges2',
           fill_color="blue", line_color="white", alpha=0.5)
    p.y_range.start = 0
    p.legend.location = "center_right"
    p.legend.background_fill_color = "#fefefe"
    p.xaxis.axis_label = 'Ampiezze (mV)'
    p.yaxis.axis_label = 'N prese dati'
    p.xaxis.axis_label_text_font_size='13pt'
    p.yaxis.axis_label_text_font_size='13pt'    
    p.grid.grid_line_color="white"
    return p


def make_plot2(title,source3):
    '''Plots a single waveform'''
    p = figure(title=title, tools="crosshair,pan,reset,save,wheel_zoom", background_fill_color="black")
    p.line('t','V',source=source3, line_color="lime", line_width=1, alpha=1, legend_label="Waveform")

    
    p.legend.location = "bottom_left"
    p.legend.background_fill_color = "#fefefe"
    p.yaxis.axis_label = 'Ampiezza (mV)'
    p.xaxis.axis_label = 'Tempo (ns)'

    p.xaxis.axis_label_text_font_size='13pt'
    p.yaxis.axis_label_text_font_size='13pt'    
    p.grid.grid_line_color="white"
    return p





A0=np.zeros(100)  #array inizializzati, ampiezze delle singole prese dati
A0h=np.ones(100)  #istogramma delle ampiezze
A0e=np.linspace(0,100,100,endpoint=1)   #posizione della colonna dell'istogramma
A0h=np.exp(-(A0e[:-1]-50.0)**2/500.0)
source=ColumnDataSource(data=dict(hist=A0h,edges1=A0e[:-1],edges2=A0e[1:])) #source per plottare gli istogrammi
source2=ColumnDataSource(data=dict(x1=np.zeros(100),y1=np.zeros(100)))      #source per plottare il fit degli istogrammi
source3=ColumnDataSource(data=dict(t=np.linspace(0,1000,1000),V=np.zeros(1000),Vfit=np.zeros(1000))) #source per plottare la waveform corrente
p=make_plot('Istogramma 0',source)    #inizializzazione della figura
p2=make_plot2('Attuale presa dati',source3)
mean_Ampl_label = Label(x=250, y=200, x_units='screen', y_units='screen',
                 text='', render_mode='canvas',
                 border_line_color='black', border_line_alpha=1.0,
                 background_fill_color='white', background_fill_alpha=1.0,visible=False)
p.add_layout(mean_Ampl_label)
acquisizione=False         #controlla che il programma stia acquisendo dati, inizializzato a falso
update_menu_check=False    #controllo se necessario fittare i dati dell'istogramma
Area_text=TextAreaInput(value=Default_text,rows=6)
Area_text_data=StringIO(Area_text.value)
df_wfr=pd.read_csv(Area_text_data,index_col=0, delimiter=',')
acquisitionMananger =WaveformReader (Volt_rangeA = df_wfr['Val']['Channel_A_range'],
                                    Volt_rangeB = df_wfr['Val']['Channel_B_range'],
                                    Trigger_value = df_wfr['Val']['Trigger_value'],
                                    Trigger_type = df_wfr['Val']['Trigger_type'],
                                    preTriggerSamples=df_wfr['Val']['preTriggerSamples'],
                                    postTriggerSamples=df_wfr['Val']['postTriggerSamples'] ) #Scelta della classe python che si occupa della lettura delle waveform
nome_db=TextInput(title='Nome del database di memorizzazione:',value='Prova.db') #Widget per il cambiamento del nome del file di database
dbw = DatabaseWrite (nome_db.value, acquisitionMananger) #classe python che si occupa della gestione in memoria delle waveform


#FUNZIONI PER L'AGGIORNAMENTO DEI BOTTONI------------------------------------------------------------------------------------------------


def update_button0():

  '''Bottone per il fitting con la Landau'''

  A0h,A0e,A0hfit,p0,p0cov=fit_hist(A0,method=0)
  p0err=np.sqrt(np.diag(p0cov))
  source2.data=dict(x1=A0e,y1=A0hfit)
  #chi2=UF.chi2(A0h,A0hfit)
  mean_Ampl,mean_Ampl_err=UF.Landau_error(A0e,p0[0],p0[1],p0[2],p0err[0],p0err[1],p0err[2])
  print(mean_Ampl,mean_Ampl_err)
  p.line('x1','y1' ,source=source2 ,line_color="red", line_width=4, alpha=0.7, legend_label='Fit con Landau')

  text='Carica misurata: %d +/- %d e'%(mean_Ampl*Gain,mean_Ampl_err*Gain)

  mean_Ampl_label.update(visible=True,text=text)

def update_button1():

  '''Bottone per il fitting della Landau+ la Gaussiana'''

  A0h,A0e,A0hfit,p0,p0cov=fit_hist(A0,method=1)
  p0err=np.sqrt(np.diag(p0cov))
  source2.data=dict(x1=A0e,y1=A0hfit)
  #chi2=UF.chi2(A0h,A0hfit)
  mean_Ampl,mean_Ampl_err=UF.Landau_error(A0e,p0[0],p0[2],p0[4],p0err[0],p0err[2],p0err[4])
  print(mean_Ampl,mean_Ampl_err)
  p.line('x1','y1',source=source2 ,line_color="green", line_width=4, alpha=0.7, legend_label='Fit con Landau+Gaussiana')


  text='Carica misurata: %d +/- %d '%(mean_Ampl*Gain,mean_Ampl_err*Gain)

  mean_Ampl_label.update(visible=True,text=text)

def update_button2():

  '''Bottone per l'acquisizione dei dati, controlla l'esecuzione della funzione
ciclo_acq. quando la variabile acquisizione=True
    il programma sta acquisendo dati e il bottone lo ferma, e viceversa
  '''

  global acquisizione,t,C1,update_menu_check
  if acquisizione==False:
    print ('Inizio acq')
    acquisizione=True
    bottone2.update(label='Stop',button_type='danger')
  else:
    acquisizione=False

    print ('Stop')
     
    bottone2.update(label='Inizio acquisizione',button_type='success')

def update_button3():
  '''Function that resets database when button3 is clicked'''
  bottone4.update(visible=True)
  bottone5.update(visible=True)

def update_button4():
  global dbw
  dbw.reset_database() 

  dbw = DatabaseWrite (nome_db.value, acquisitionMananger) #classe python che si occupa della gestione in memoria delle waveform
  bottone4.update(visible=False)
  bottone5.update(visible=False)

def update_button5():

  bottone4.update(visible=False)
  bottone5.update(visible=False)

def update_button6():


  global acquisizione,t,C1,update_menu_check


  update_menu_check=True
  tlist,C1list,C2list=dbw.readWaveforms()
  C1=np.array(C1list)
  C2=np.array(C2list)
  t=np.array(tlist)
  t=t/1000
  update_menu(0,0,0)


  bottone0.update(visible=True)
  bottone1.update(visible=True)

def update_nome_db(attr,old,new):
  global dbw  
  dbw = DatabaseWrite (nome_db.value, acquisitionMananger) 

def update_Area_text(attr,old,new):
  global dbw,acquisitionMananger
  Area_text_data=StringIO(Area_text.value)
  
  df_wfr=pd.read_csv(Area_text_data,index_col=0, delimiter=',')
  acquisitionMananger.close()
  acquisitionMananger =WaveformReader (Volt_rangeA = df_wfr['Val']['Channel_A_range'],
                                    Volt_rangeB = df_wfr['Val']['Channel_B_range'],
                                    Trigger_value = df_wfr['Val']['Trigger_value'],
                                    Trigger_type = df_wfr['Val']['Trigger_type'],
                                    preTriggerSamples=df_wfr['Val']['preTriggerSamples'],
                                    postTriggerSamples=df_wfr['Val']['postTriggerSamples'] ) #Scelta della classe python che si occupa della lettura delle waveform

  dbw = DatabaseWrite (nome_db.value, acquisitionMananger) 

def ciclo_acq():
  global t,C1

  if acquisizione==True:
    t1=time()

    while (time()-t1)<0.8:
      dbw.run() 
   
    t_,C1_,C2_=dbw.readlastWaveform() 

    source3.data=dict(t=t_,V=C1_)
    titolo='Attuale presa dati numero:'+str(dbw.it)
    p2.title.text=titolo
    #t,C1,C2=dbw.readWaveforms()
    #t_=np.array(dbw.t)
    #C1_=np.array(dbw.C1)
    infobox.update(text='Presa misure in corso...')




def update_menu(attr,old,new):
  
  global A0
  if update_menu_check==False:
    return

  infobox.update(text="Calcolo dell'istogrammma, attendere ...")

  if menu.value=='Gaussiana biforcuta':
    p.title.text='Attendere ...'
    A0,mu0,B0=Amplitude_dist(t,C1,mode=0,nfiles=0)
    A0h,A0e=np.histogram(A0,range=(0.1,100),bins=100)
    source.data=dict(hist=A0h,edges1=A0e[:-1],edges2=A0e[1:])
    p.title.text='Istogramma 0'

  elif menu.value=='Gaussiana skew':
    p.title.text='Attendere ...'
    A0,mu0,B0=Amplitude_dist(t,C1,mode=1,nfiles=0)
    A0h,A0e=np.histogram(A0,range=(0.1,100),bins=100)
    source.data=dict(hist=A0h,edges1=A0e[:-1],edges2=A0e[1:])
    p.title.text='Istogramma 0'


  elif menu.value=='Ricerca minimi semplice':
    p.title.text='Attendere ...'
    A0,mu0,B0=Amplitude_dist(t,C1,mode=2,nfiles=0)
    A0h,A0e=np.histogram(A0,range=(0.1,100),bins=100)
    source.data=dict(hist=A0h,edges1=A0e[:-1],edges2=A0e[1:])
    p.title.text='Istogramma 0'

  infobox.update(text="Programma pronto per iniziare una nuova presa dati")

bottone0=Button(label='Fit con Landau',visible=False)
bottone1=Button(label='Fit con Landau+Gaussiana',visible=False)
bottone2=Button(label='Iniziare presa misure',button_type='success')
bottone3=Button(label='Reset del database',button_type='danger')
bottone4=Button(label='Conferma',button_type='success',width=200,visible=False)
bottone5=Button(label='Annulla',button_type='danger',width=200,visible=False)
bottone6=Button(label='Analizza Dati',button_type='primary')
menu=Select(options=['Gaussiana biforcuta','Gaussiana skew','Ricerca minimi semplice'],value='Gaussiana biforcuta',title='Fit delle singole prese dati')
infobox=Paragraph(text='Programma pronto per iniziare a prendere misure',width=400)

Area_text.on_change('value',update_Area_text)
menu.on_change('value',update_menu)
nome_db.on_change('value',update_nome_db)
bottone0.on_click(update_button0)
bottone1.on_click(update_button1)
bottone2.on_click(update_button2)
bottone3.on_click(update_button3)
bottone4.on_click(update_button4)
bottone5.on_click(update_button5)
bottone6.on_click(update_button6)
confirmation_buttons=row(bottone4,bottone5)
fitting_buttons=column(bottone2,bottone0,bottone1,bottone6,bottone3,confirmation_buttons,menu,nome_db,Area_text,infobox)


curdoc().add_root(row(fitting_buttons, p,p2, width=1200))
curdoc().add_periodic_callback(ciclo_acq, 1000)
curdoc().title = "Istogramma"


