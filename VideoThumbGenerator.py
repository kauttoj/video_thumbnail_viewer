# -*- coding: utf-8 -*-
"""
Created on Wed Nov 22 12:26:27 2017

@author: Jannek
"""

import os
import os.path
import subprocess
import matplotlib.pyplot as plt
import matplotlib.image as Image
from functools import partial
from multiprocessing import Pool
import matplotlib.patheffects as PathEffects
import time

def get_video_frames(points,INFILE,TEMP_FILE,FFMPEG_PATH):

    img = []

    for point in points:

        cmd = '%sffmpeg.exe -y -ss %i -i "%s" -vframes 1 "%s"' % (FFMPEG_PATH,point,INFILE,TEMP_FILE)
        subprocess.run(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        #process.wait()

        try:
            img.append(Image.imread(TEMP_FILE))
            if os.path.isfile(TEMP_FILE):
                os.remove(TEMP_FILE)
            assert(img[-1].shape[0]>10 and img[-1].shape[1]>10)
        except:
            if os.path.isfile(TEMP_FILE):
                os.remove(TEMP_FILE)
            return None

    return img

def get_sec(time_str):
    h, m, s = time_str.split(':')
    return int(h)*3600 + int(m)*60 + int(float(s))

def get_video_duration(INFILE,FFMPEG_PATH):

    cmd = '%sffmpeg.exe -i "%s" -f null' % (FFMPEG_PATH,INFILE)
    process = subprocess.run(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    #process.wait()

    b = str(process.stderr)#.readlines())

    ind = b.find('Duration: ')

    if ind<0:
        return 0
    try:
        duration = get_sec(b[(ind + 10):(ind + 21)])
    except:
        return 0

    return duration

def get_folder_index(duration,OUTFOLDERS,OUTTIMES):

    folder_index = None
    if duration<OUTTIMES[0]:
        folder_index=0
    elif duration>=OUTTIMES[-1]:
        folder_index = len(OUTFOLDERS)-1
    else:
        for i in range(len(OUTTIMES)-1):
            if duration>=OUTTIMES[i] & duration<OUTTIMES[i+1]:
                folder_index=i+1                
                
    return folder_index


def process_file(k,DATA):
    
    #---------------------------    
    output = DATA['alloutfiles'][k]
    INPUT_FILE = DATA['allfiles'][k]
    OUTFOLDER = DATA['OUTFOLDER']
    OUTTIMES = DATA['OUTTIMES']
    TIMEPOINTS = DATA['TIMEPOINTS']
    FFMPEG_PATH = DATA['FFMPEG_PATH']
    SIZE = DATA['SIZE']    
    #---------------------------        
    
    textfiles = []
        
    duration = get_video_duration(INPUT_FILE,FFMPEG_PATH)

    if duration<5:
        #failed_files[k] = 1
        if duration==0:
            print('... FAILED (zero duration) %s' % INPUT_FILE)
        else:
            print('... FAILED (too short) %s' % INPUT_FILE)
        return textfiles

    folder_index = get_folder_index(duration, OUTFOLDER, OUTTIMES)

    outfile = OUTFOLDER[folder_index] + os.sep + output
    
    if os.path.isfile(outfile):
        textfiles = (folder_index, (OUTFOLDER[folder_index] + ';' + output + ';' + INPUT_FILE))
        print('... DONE (old found) %s' % INPUT_FILE)
        return textfiles

    points = [round(duration*x) for x in TIMEPOINTS]

    img = get_video_frames(points,INPUT_FILE,outfile,FFMPEG_PATH)

    if img is None:
        #failed_files[k] = 1
        print('... FAILED (snapshot failed) %s' % INPUT_FILE)
        return textfiles

    aspect = img[0].shape[0] / img[0].shape[1]

    N_FRAMES = len(points)
    fig1 = plt.figure(figsize=(SIZE*1.02,(SIZE*aspect/N_FRAMES)*1.07))
    dx = 0.98/N_FRAMES
    dxx = 0.020/(N_FRAMES-1)
    middle = round(N_FRAMES/2)-1
    for i in range(N_FRAMES):

        ax = fig1.add_axes([i*(dx+dxx),0,dx,0.9345794392523364])
        ax.imshow(img[i],aspect='auto')
        ax.axis('off')
        txt = ax.text(0.05,0.95,'%is' % points[i],horizontalalignment='center',size=12,verticalalignment='center',transform = ax.transAxes,color='black')
        txt.set_path_effects([PathEffects.withStroke(linewidth=2, foreground='w')])
        if i==middle:
            ax.set_title(INPUT_FILE,fontsize=11)

    fig1.savefig(outfile)
    plt.close(fig1)

    textfiles = (folder_index, (OUTFOLDER[folder_index] + ';' + output + ';' + INPUT_FILE))

    print('... DONE %s' % INPUT_FILE)

    return textfiles

class VideoThumbGenerator(object):

    def __init__(self,
                 TIMEPOINTS = (0.30,0.60,0.80),
                 OUTPATH = r'D:\Downloads\thumbnail_testing',
                 INFOLDER = r'D:\Downloads',
                 SIZE = 17, # figure width in inches
                 OUTTIMES = (10,), # separations, in minutes
                 NWORKERS = 3,
                 FFMPEG_PATH = r'C:\Users\JanneK\PycharmProjects\VideoThumbViewer' + os.sep,
                 EXTENSIONS = ('.mp4','.avi','.mov','.mpg','.wmv','.mkv','.m4v','.flv')):

        self.TIMEPOINTS = TIMEPOINTS
        self.OUTPATH = OUTPATH
        self.INFOLDER = INFOLDER
        self.SIZE = SIZE
        self.OUTTIMES = OUTTIMES
        self.NWORKERS = NWORKERS
        self.FFMPEG_PATH = FFMPEG_PATH
        self.EXTENSIONS = EXTENSIONS

    def filesearch(self,PATH,FILES):

        a = os.listdir(PATH)
        for i in a:
            file = PATH + os.sep + i
            if os.path.isdir(file):
                FILES = self.filesearch(file,FILES)
            elif os.path.isfile(file):
                #name = i[0:-4]
                ext = i[-4:]
                if ext in self.EXTENSIONS:
                    FILES.append(file)
        return FILES

    def fileparts(self,line):
        drive, path = os.path.splitdrive(line)
        path, filename = os.path.split(path)
        if len(filename)>4 and filename[-4] == '.':
            extension = filename[-4:]
            filename = filename[0:-4]
        else:
            extension = ''
        return [drive + path, filename, extension]

    def run(self):
    #if __name__ == '__main__':

        assert(os.path.isdir(self.INFOLDER))

        OUTTIMES = [round(x) for x in self.OUTTIMES]
        OUTTIMES = list(set(OUTTIMES))

        assert(all([a>0 & a<1000 for a in OUTTIMES]));
        assert(0<len(OUTTIMES)<100)

        print('\nphase 1: setting parameters')

        if len(OUTTIMES)==0:
            OUTFOLDER = [self.OUTPATH]
        else:
            OUTFOLDER = ['']*(len(OUTTIMES)+1)
            OUTFOLDER[0] = self.OUTPATH+os.sep+'less_than_%imin' % OUTTIMES[0]
            for i in range(1,len(OUTTIMES)):
                OUTFOLDER[i] = self.OUTPATH + os.sep + 'between_%imin_and_%imin' % (OUTTIMES[i-1],OUTTIMES[i])
            OUTFOLDER[len(OUTTIMES)] = self.OUTPATH + os.sep + 'over_%imin' % OUTTIMES[-1]
            assert(len(OUTTIMES) == len(OUTFOLDER)-1);

        for i in OUTFOLDER:
            if not os.path.isdir(i):
                os.makedirs(i)
                assert(os.path.isdir(i))

        allfiles = self.filesearch(self.INFOLDER, [])

        alloutfiles=[]
        for i in range(len(allfiles)):
            [a,b,c] = self.fileparts(allfiles[i])
            k=0
            newname = b + '.jpg'
            while 1:
                if newname in alloutfiles:
                    k+=1
                    newname = b + '_' + str(k) + '.jpg'
                else:
                    break
                if k>100:
                    raise('Too many files with same name! Check your files')
            alloutfiles.append(newname)

        assert(len(alloutfiles)==len(allfiles))
        print('Total %i files found\n' % len(allfiles))

        N = len(allfiles)
        assert(N<10000)  # lets not go grazy

        plt.close('all')
    
        # into seconds
        OUTTIMES = [x*60 for x in OUTTIMES]
    
        DATA = {}    
        DATA['alloutfiles']=alloutfiles
        DATA['allfiles'] = allfiles
        DATA['OUTFOLDER'] = OUTFOLDER
        DATA['OUTTIMES']= OUTTIMES
        DATA['TIMEPOINTS'] = self.TIMEPOINTS
        DATA['FFMPEG_PATH'] = self.FFMPEG_PATH
        DATA['SIZE'] = self.SIZE

        #res = process_file(9,DATA)

        print('\nphase 2: generating thumbnails')
        
        start_time = time.time()

        if self.NWORKERS>1:

            pool = Pool(processes=self.NWORKERS)        
            pool_result = pool.map(partial(process_file,DATA=DATA),list(range(len(allfiles))))
            pool.close()
            pool.join()
            
            textfiles = [[]]*len(allfiles)        
            
            for i,result in enumerate(pool_result):
                textfiles[i] = result
#
        else:
            textfiles = ['']*len(allfiles)
            for k in range(len(allfiles)):
                textfiles[k] = process_file(DATA=DATA,k=k)
#            
#        for k in range(len(allfiles)):
        N1= len(textfiles)
        elapsed =  time.time()-start_time
        print('..summary: %i files processed in %is (%f videos/sec)' % (N1,round(elapsed),elapsed/N1))

        print('\nphase 3: writing textfiles')
        
        textfiles = [i for i in textfiles if len(i)>0]
        N2 = len(textfiles)
        
        print('..summary: %i/%i files failed' % (N1-N2,N1))

        textfiles_sorted = [[] for _ in range(len(OUTFOLDER))]
        for i in textfiles:
            ind = i[0]
            data = i[1]
            textfiles_sorted[ind].append(data)

        for i,texts in enumerate(textfiles_sorted):
            filename = OUTFOLDER[i] + os.sep + 'MyVideoThumbs.dat'
            with open(filename,'w',encoding='utf8') as file:
                file.write('\n'.join(texts))
            print('... textfile written: %s' % filename )

        print('\n--- ALL DONE! ---\n')
    

if __name__ == '__main__':
    __spec__ = "ModuleSpec(name='builtins', loader=<class '_frozen_importlib.BuiltinImporter'>)"
    obj = VideoThumbGenerator(OUTPATH=r'H:\Downloads\conn\video_preview_images',INFOLDER=r'H:\Downloads\conn',FFMPEG_PATH='',NWORKERS=1)
    obj.run()
