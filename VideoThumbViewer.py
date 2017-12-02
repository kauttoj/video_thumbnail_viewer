#!/usr/bin/env python

# Small wxPython application to generate and browse video thumbnails and single-click play videos
#
# Allows fast browsing of large video collections
#
# GUI is based on wxGrid view and Mega Grid Example
# thumbnail generator uses ffmpeg, which needs to be installed and found
#
# USAGE: 
#   1. (Set thumbnail image settings OR) skip to use defaults
#   2. Choose a directory and generate thumbnails. This takes several minutes and creates a file MyVideoThumbs.dat, one for each subfolder
#   3. Open MyVideoThumbs.dat file
#   4. Browse files, click thumbnail to open video with default system video player (changable through your system settings)    

# 2017 Janne Kauttonen

import wx
import wx.grid as Grid
import get_image_size
import math
import os
from os import startfile
from threading import Thread
from pubsub import pub
from VideoThumbGenerator import VideoThumbGenerator

#import images

#---------------------------------------------------------------------------

WIDTH = 1300
HEIGHT = 800
FIGURES_PER_PAGE = 200

def scale_bitmap(bitmap, width, height):
    image = bitmap.ConvertToImage()
    image = image.Scale(width, height, wx.IMAGE_QUALITY_HIGH)
    result = wx.Bitmap(image)
    return result  

class MegaTable(Grid.GridTableBase):
    """
    A custom wx.Grid Table using user supplied data
    """
    def __init__(self, data, colnames, plugins):
        """data is a list of the form
        [(rowname, dictionary),
        dictionary.get(colname, None) returns the data for column
        colname
        """
        # The base class must be initialized *first*
        Grid.GridTableBase.__init__(self)
        self.data = data
        self.colnames = colnames
        self.plugins = plugins or {}
        # XXX
        # we need to store the row length and column length to
        # see if the table has changed size
        self._rows = self.GetNumberRows()
        self._cols = self.GetNumberCols()

    def GetNumberCols(self):
        return len(self.colnames)

    def GetNumberRows(self):
        return len(self.data)

    def GetColLabelValue(self, col):
        return self.colnames[col]

    def GetRowLabelValue(self, row):
        return "%03d" % int(self.data[row][0])

    def GetValue(self, row, col):
        return str(self.data[row][1].get(self.GetColLabelValue(col), ""))

    def GetRawValue(self, row, col):
        return self.data[row][1].get(self.GetColLabelValue(col), "")

    def SetValue(self, row, col, value):
        pass
        #self.data[row][1][self.GetColLabelValue(col)] = value

    def ResetView(self, grid):
        """
        (Grid) -> Reset the grid view.   Call this to
        update the grid if rows and columns have been added or deleted
        """
        grid.BeginBatch()

        for current, new, delmsg, addmsg in [
            (self._rows, self.GetNumberRows(), Grid.GRIDTABLE_NOTIFY_ROWS_DELETED, Grid.GRIDTABLE_NOTIFY_ROWS_APPENDED),
            (self._cols, self.GetNumberCols(), Grid.GRIDTABLE_NOTIFY_COLS_DELETED, Grid.GRIDTABLE_NOTIFY_COLS_APPENDED),
        ]:

            if new < current:
                msg = Grid.GridTableMessage(self,delmsg,new,current-new)
                grid.ProcessTableMessage(msg)
            elif new > current:
                msg = Grid.GridTableMessage(self,addmsg,new-current)
                grid.ProcessTableMessage(msg)
                self.UpdateValues(grid)

        grid.EndBatch()

        self._rows = self.GetNumberRows()
        self._cols = self.GetNumberCols()
        
        for i in range(self._rows):        
            grid.SetRowSize(i,self.data[i][1]['dims'][1])
        
        # update the column rendering plugins
        self._updateColAttrs(grid)

        # update the scrollbars and the displayed part of the grid
        grid.AdjustScrollbars()
        grid.ForceRefresh()


    def UpdateValues(self, grid):
        """Update all displayed values"""
        # This sends an event to the grid table to update all of the values
        msg = Grid.GridTableMessage(self, Grid.GRIDTABLE_REQUEST_VIEW_GET_VALUES)
        grid.ProcessTableMessage(msg)

    def _updateColAttrs(self, grid):
        """
        wx.Grid -> update the column attributes to add the
        appropriate renderer given the column name.  (renderers
        are stored in the self.plugins dictionary)

        Otherwise default to the default renderer.
        """
        col = 0

        for colname in self.colnames:
            attr = Grid.GridCellAttr()
            if colname in self.plugins:
                renderer = self.plugins[colname](self)

                if renderer.colSize:
                    grid.SetColSize(col, renderer.colSize)

                if renderer.rowSize:
                    grid.SetDefaultRowSize(renderer.rowSize)

                attr.SetReadOnly(True)
                attr.SetRenderer(renderer)

            grid.SetColAttr(col, attr)
            col += 1

    # ------------------------------------------------------
    # begin the added code to manipulate the table (non wx related)
    def AppendRow(self, row):
        #print('append')
        entry = {}

        for name in self.colnames:
            entry[name] = "Appended_%i"%row

        # XXX Hack
        # entry["A"] can only be between 1..4
        entry["video"] = 1
        self.data.insert(row, ["Append_%i"%row, entry])

    def DeleteCols(self, cols):
        """
        cols -> delete the columns from the dataset
        cols hold the column indices
        """
        # we'll cheat here and just remove the name from the
        # list of column names.  The data will remain but
        # it won't be shown
        deleteCount = 0
        cols = cols[:]
        cols.sort()

        for i in cols:
            self.colnames.pop(i-deleteCount)
            # we need to advance the delete count
            # to make sure we delete the right columns
            deleteCount += 1

        if not len(self.colnames):
            self.data = []

    def DeleteRows(self, rows):
        """
        rows -> delete the rows from the dataset
        rows hold the row indices
        """
        deleteCount = 0
        rows = rows[:]
        rows.sort()

        for i in rows:
            self.data.pop(i-deleteCount)
            # we need to advance the delete count
            # to make sure we delete the right rows
            deleteCount += 1

    def SortColumn(self, col):
        """
        col -> sort the data based on the column indexed by col
        """
        name = self.colnames[col]
        _data = []

        for row in self.data:
            rowname, entry = row
            _data.append((entry.get(name, None), row))

        _data.sort()
        self.data = []

        for sortvalue, row in _data:
            self.data.append(row)

    # end table manipulation code
    # ----------------------------------------------------------


# --------------------------------------------------------------------
# Sample wx.Grid renderers

class MegaImageRenderer(Grid.GridCellRenderer):
    def __init__(self, table):
        """
        Image Renderer Test.  This just places an image in a cell
        based on the row index.  There are N choices and the
        choice is made by  choice[row%N]
        """
        Grid.GridCellRenderer.__init__(self)
        self.table = table

        self.colSize = None
        self.rowSize = None

    def Draw(self, grid, attr, dc, rect, row, col, isSelected):
        #bmp = self._choices[ choice % len(self._choices)]()
        bmp = wx.Bitmap(grid.GetCellValue(row,col))        
        bmp = scale_bitmap(bmp,self.table.data[row][1]['dims'][0]-2,self.table.data[row][1]['dims'][1]-2) 
        
        image = wx.MemoryDC()
        image.SelectObject(bmp)

        # clear the background
        dc.SetBackgroundMode(wx.SOLID)

        if isSelected:
            dc.SetBrush(wx.Brush(wx.BLUE, wx.BRUSHSTYLE_SOLID))
            dc.SetPen(wx.Pen(wx.BLUE, 1, wx.PENSTYLE_SOLID))
        else:
            dc.SetBrush(wx.Brush(wx.WHITE, wx.BRUSHSTYLE_SOLID))
            dc.SetPen(wx.Pen(wx.WHITE, 1, wx.PENSTYLE_SOLID))
        dc.DrawRectangle(rect)

        # copy the image but only to the size of the grid cell
        width, height = bmp.GetWidth(), bmp.GetHeight()
                
        if width > rect.width-2:
            width = rect.width-2

        if height > rect.height-2:
            height = rect.height-2                             

        dc.Blit(rect.x+1, rect.y+1, width, height,
                image,
                0, 0, wx.COPY, True)


class MegaFontRenderer(Grid.GridCellRenderer):
    def __init__(self, table, color="blue", font="ARIAL", fontsize=8):
        """Render data in the specified color and font and fontsize"""
        Grid.GridCellRenderer.__init__(self)
        self.table = table
        self.color = color
        self.font = wx.Font(fontsize, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, 0, font)
        self.selectedBrush = wx.Brush("blue", wx.BRUSHSTYLE_SOLID)
        self.normalBrush = wx.Brush(wx.WHITE, wx.BRUSHSTYLE_SOLID)
        self.colSize = None
        self.rowSize = 200

    def Draw(self, grid, attr, dc, rect, row, col, isSelected):
        # Here we draw text in a grid cell using various fonts
        # and colors.  We have to set the clipping region on
        # the grid's DC, otherwise the text will spill over
        # to the next cell
        dc.SetClippingRegion(rect)

        # clear the background
        dc.SetBackgroundMode(wx.SOLID)

        if isSelected:
            dc.SetBrush(wx.Brush(wx.BLUE, wx.BRUSHSTYLE_SOLID))
            dc.SetPen(wx.Pen(wx.BLUE, 1, wx.PENSTYLE_SOLID))
        else:
            dc.SetBrush(wx.Brush(wx.WHITE, wx.BRUSHSTYLE_SOLID))
            dc.SetPen(wx.Pen(wx.WHITE, 1, wx.PENSTYLE_SOLID))
        dc.DrawRectangle(rect)

        text = self.table.GetValue(row, col)
        dc.SetBackgroundMode(wx.SOLID)

        # change the text background based on whether the grid is selected
        # or not
        if isSelected:
            dc.SetBrush(self.selectedBrush)
            dc.SetTextBackground("blue")
        else:
            dc.SetBrush(self.normalBrush)
            dc.SetTextBackground("white")

        dc.SetTextForeground(self.color)
        dc.SetFont(self.font)
        dc.DrawText(text, rect.x+1, rect.y+1)

        # Okay, now for the advanced class :)
        # Let's add three dots "..."
        # to indicate that that there is more text to be read
        # when the text is larger than the grid cell

        width, height = dc.GetTextExtent(text)

        if width > rect.width-2:
            width, height = dc.GetTextExtent("...")
            x = rect.x+1 + rect.width-2 - width
            dc.DrawRectangle(x, rect.y+1, width+1, height)
            dc.DrawText("...", x, rect.y+1)

        dc.DestroyClippingRegion()


# --------------------------------------------------------------------
# Sample Grid using a specialized table and renderers that can
# be plugged in based on column names

class MegaGrid(Grid.Grid):
    def __init__(self, parent, data, colnames, plugins=None):
        """parent, data, colnames, plugins=None
        Initialize a grid using the data defined in data and colnames
        (see MegaTable for a description of the data format)
        plugins is a dictionary of columnName -> column renderers.
        """

        # The base class must be initialized *first*
        Grid.Grid.__init__(self, parent, -1)
        self._table = MegaTable(data, colnames, plugins)
        self.SetTable(self._table)
        self._plugins = plugins

        self.Bind(Grid.EVT_GRID_LABEL_RIGHT_CLICK, self.OnLabelRightClicked)

    def Reset(self):
        """reset the view based on the data in the table.  Call
        this when rows are added or destroyed"""
        self._table.ResetView(self)

    def OnLabelRightClicked(self, evt):
        # Did we click on a row or a column?
        row, col = evt.GetRow(), evt.GetCol()
        if row == -1: self.colPopup(col, evt)
        elif col == -1: self.rowPopup(row, evt)

    def rowPopup(self, row, evt):
        """(row, evt) -> display a popup menu when a row label is right clicked"""
        appendID = wx.NewId()
        deleteID = wx.NewId()
        x = self.GetRowSize(row)/2

        if not self.GetSelectedRows():
            self.SelectRow(row)

        menu = wx.Menu()
        xo, yo = evt.GetPosition()
        menu.Append(appendID, "Append Row")
        menu.Append(deleteID, "Delete Row(s)")

        def append(event, self=self, row=row):
            self._table.AppendRow(row)
            self.Reset()

        def delete(event, self=self, row=row):
            rows = self.GetSelectedRows()
            self._table.DeleteRows(rows)
            self.Reset()

        self.Bind(wx.EVT_MENU, append, id=appendID)
        self.Bind(wx.EVT_MENU, delete, id=deleteID)
        self.PopupMenu(menu)
        menu.Destroy()
        return


    def colPopup(self, col, evt):
        """(col, evt) -> display a popup menu when a column label is
        right clicked"""
        x = self.GetColSize(col)/2
        menu = wx.Menu()
        id1 = wx.NewId()
        sortID = wx.NewId()

        xo, yo = evt.GetPosition()
        self.SelectCol(col)
        cols = self.GetSelectedCols()
        self.Refresh()
        menu.Append(id1, "Delete Col(s)")
        menu.Append(sortID, "Sort Column")

        def delete(event, self=self, col=col):
            cols = self.GetSelectedCols()
            self._table.DeleteCols(cols)
            self.Reset()

        def sort(event, self=self, col=col):
            self._table.SortColumn(col)
            self.Reset()

        self.Bind(wx.EVT_MENU, delete, id=id1)

        if len(cols) == 1:
            self.Bind(wx.EVT_MENU, sort, id=sortID)

        self.PopupMenu(menu)
        menu.Destroy()
        return


colnames = ["video"]
data = []

class MegaFontRendererFactory:
    def __init__(self, color, font, fontsize):
        """
        (color, font, fontsize) -> set of a factory to generate
        renderers when called.
        func = MegaFontRenderFactory(color, font, fontsize)
        renderer = func(table)
        """
        self.color = color
        self.font = font
        self.fontsize = fontsize

    def __call__(self, table):
        return MegaFontRenderer(table, self.color, self.font, self.fontsize)

#---------------------------------------------------------------------------
class MyThread(Thread):
    """Test Worker Thread Class."""
 
    #----------------------------------------------------------------------
    def __init__(self,OUTPATH,INFOLDER,FFMPEG_PATH):
        """Init Worker Thread Class."""
        Thread.__init__(self)
        self.obj = VideoThumbGenerator(OUTPATH=OUTPATH,INFOLDER=INFOLDER,FFMPEG_PATH=FFMPEG_PATH)
        self.start()    # start the thread
 
    #----------------------------------------------------------------------
    def run(self):
        """Run Worker Thread."""
        # This is the code executing in the new thread.
        try:
            self.obj.run()
            msg = 1           
        except Exception as inst:
            print(inst)
            msg = 2
        pub.sendMessage("generatorFinished",msg=msg)                      
        
class TestFrame(wx.Frame):
    def __init__(self, parent=None, plugins={"text":MegaFontRendererFactory("red", "ARIAL", 8),
                                        "video":MegaImageRenderer}):
        wx.Frame.__init__(self, None, -1,
                         "Video Thumbnail Viewer (ver 1)", size=(WIDTH,HEIGHT))
        self.panel_top = wx.Panel(self, size=(WIDTH,HEIGHT-100),pos=(0,0),style=wx.SIMPLE_BORDER)        
        #self.panel_top.SetBackgroundColour('#FDDF99')
        self.panel_bottom = wx.Panel(self, size=(WIDTH,100),pos=(0,HEIGHT-100),style=wx.SIMPLE_BORDER)        
        #self.panel_top.SetBackgroundColour('RED')
        
        pub.subscribe(self.generatorFinished,('generatorFinished'))

        self.btn_generate = wx.Button(self.panel_bottom,-1,"Generate")#,size=(150,40),pos=(0.30*WIDTH,HEIGHT-50))
        self.btn_generate.Bind(wx.EVT_BUTTON,self.onClicked_generate)
        self.btn_prev = wx.Button(self.panel_bottom,-1,"Previous")#,size=(150,40),pos=(0.30*WIDTH,HEIGHT-50)) 
        self.btn_prev.Bind(wx.EVT_BUTTON,self.onClicked_prev)    
        self.btn_next = wx.Button(self.panel_bottom,-1,"Next")#,size=(150,40),pos=(0.70*WIDTH,HEIGHT-50)) 
        self.btn_next.Bind(wx.EVT_BUTTON,self.onClicked_next)          
        self.infotext = wx.TextCtrl(self.panel_bottom, -1, "",style = wx.TE_READONLY | wx.TE_CENTRE )  # | wx.BORDER_NONE
       
        panel_bottom_sizer = wx.BoxSizer(wx.HORIZONTAL)
        panel_bottom_sizer.Add(self.btn_generate, 0, wx.ALIGN_CENTER, 0)
        panel_bottom_sizer.Add(self.btn_prev,0,wx.ALIGN_CENTER,0)
        panel_bottom_sizer.Add(self.btn_next,0,wx.ALIGN_CENTER,0)
        panel_bottom_sizer.Add(self.infotext,wx.EXPAND,wx.ALIGN_CENTER,0)
        self.panel_bottom.SetSizer(panel_bottom_sizer)    

        self.picPaths = []        
        self.COLWIDTH = WIDTH-70
        self.MAX_ROWHEIGHT = int(0.60*WIDTH)
        self.PageNum = 0
        self.TotalPages = 0
        self.totalImages = 0
        self.folderPath = []

        self.grid = MegaGrid(self.panel_top, data, colnames, plugins)
        
        self.grid.Bind(wx.grid.EVT_GRID_CELL_LEFT_CLICK, self.onRightClick)
        
        self.grid.SetColLabelSize(0)
        self.grid.SetRowLabelSize(50)
        
        sizer_grid = wx.BoxSizer(wx.VERTICAL)
        sizer_grid.Add(self.grid, 1, wx.ALL)                    
        self.panel_top.SetSizer(sizer_grid) 
        
        sizer_panels = wx.BoxSizer(wx.VERTICAL)
        sizer_panels.Add(self.panel_top, 1, wx.ALL)                    
        sizer_panels.Add(self.panel_bottom, 1, wx.ALL) 
        self.SetSizer(sizer_panels)         
        
        self.grid.SetDefaultColSize(self.COLWIDTH)
        self.grid.SetDefaultRowSize(self.MAX_ROWHEIGHT)
        
        self.grid.Reset()
        
        filemenu= wx.Menu()
        dir_item=filemenu.Append(0, "&Directory","choose a folder")
        filemenu.AppendSeparator()
        
        settingmenu= wx.Menu()
        setting_item = settingmenu.Append(1, "&Properties","change generator settings")
        settingmenu.AppendSeparator()
        
        menuBar = wx.MenuBar()
        menuBar.Append(filemenu,"&File") # Adding the "filemenu" to the MenuBar
        menuBar.Append(settingmenu,"&Settings") # Adding the "filemenu" to the MenuBar
        self.SetMenuBar(menuBar)  # Adding the MenuBar to the Frame content.

        self.Bind(wx.EVT_MENU,self.onOpenDirectory,dir_item,id=0)   
        self.Bind(wx.EVT_MENU,self.onChangeParameters,setting_item,id=1) 
        
    def updateText(self,text=None):
        if text == None:
            self.infotext.SetValue("%i pictures, current page %i of %i" % (self.totalImages,self.PageNum+1,self.TotalPages))
        else:
            self.infotext.SetValue(text)  
        #self.Update()   
        self.panel_bottom.Refresh()           

    def onRightClick(self, event):
        row = event.GetRow()
        
        video_index = row + self.PageNum*FIGURES_PER_PAGE        
        
        if -1<video_index<len(self.vidPaths):
            videofile = self.vidPaths[video_index]
            startfile(videofile)
            #subprocess.call('open "%s"' % videofile)
            
    def onChangeParameters(self,event):
        pass
            
    def generatorFinished(self,msg=None):
        if msg==1:
            self.updateText(text='Generator finished! Open "MyVideoThumbs.dat" in "%s"' % self.folderPath)
            self.btn_generate.Enable()
        elif msg==2:
            self.updateText(text='Generator ran into error!')                
            self.btn_generate.Enable()
        self.infotext.SetBackgroundColour(wx.Colour(255, 255, 255, 255))        
        self.panel_bottom.Refresh()

    def onClicked_generate(self, event):

        if len(self.folderPath)==0:
            dlg = wx.MessageDialog(self,'No folders selected. Please choose a folder first.','folder selection')
        else:
            dlg = wx.MessageDialog(self, 'Generate preview screenshots for a folder\n"%s"?' % self.folderPath,'image generator', wx.YES_NO | wx.ICON_QUESTION)
            result = dlg.ShowModal()
            if result == wx.ID_YES:
                out = self.folderPath + os.sep + 'video_preview_images'
                self.updateText(text='Wait! Running image generator...')  
                self.infotext.SetBackgroundColour('RED')
                MyThread(OUTPATH=out,INFOLDER=self.folderPath,FFMPEG_PATH='')                    
                self.btn_generate.Disable()
                self.panel_bottom.Refresh()
                    
        dlg.Destroy()        

    def onClicked_next(self,event):
        newpage = self.PageNum+1
        newpage=min(newpage,self.TotalPages-1)  
        if newpage!=self.PageNum:
            self.PageNum = newpage
            self.SetData()    
            self.grid.Reset() 
            self.updateText()
    
    def onClicked_prev(self,event):
        newpage = self.PageNum-1
        newpage=max(newpage,0)  
        if newpage!=self.PageNum:
            self.PageNum = newpage
            self.SetData()    
            self.grid.Reset()  
            self.updateText()
        
    def onOpenDirectory(self,event,defaultpath = None):
        """
        Opens a DirDialog to allow the user to open a folder with pictures
        """
        dlg = wx.DirDialog(None, "Choose a directory",
                           style=wx.DD_DEFAULT_STYLE)        
        picPaths = []
        vidPaths = []
        if dlg.ShowModal() == wx.ID_OK:
            self.folderPath = dlg.GetPath()
            print(self.folderPath)

            filename = self.folderPath + os.sep + 'MyVideoThumbs.dat'

            if os.path.isfile(filename):
                picPaths,vidPaths = self.load_images(filename)
            else:
                self.updateText(text='No "MyVideoThumbs.dat" found, run generator first.\n Folder is: %s' % self.folderPath)
            #picPaths = glob.glob(self.folderPath + "\\*.jpg")
            #print(picPaths)

        if len(picPaths)>0:
            self.vidPaths = vidPaths
            self.picPaths = picPaths
            self.totalImages = len(picPaths)
            self.TotalPages = int(math.ceil(len(picPaths)/FIGURES_PER_PAGE))
            self.PageNum = 0
            self.SetData()
            self.grid.Reset()
            self.updateText()

    def load_images(self,filename):

        pics = []
        videos = []
        
        self.updateText(text='Loading images from MyVideoThumbs.dat...') 

        try:

            with open(filename,'r',encoding='utf8') as file:
                data = file.read()
            data = data.split('\n')

            for d in data:
                dd = d.split(';')
                if len(dd)==3:
                    file = dd[0] + os.sep + dd[1]
                    if os.path.isfile(file) and os.path.isfile(dd[2]):
                        pics.append(file)
                        videos.append(dd[2])
                    else:
                        print('Files %s and %s not found!\n' % (file,dd[2]))
                else:
                    print('Incorrect row format %s\n' % d)

            assert(len(pics) == len(videos))
        except:
            pass

        return pics,videos
                
    def SetData(self):
            
        ind1 = self.PageNum*FIGURES_PER_PAGE
        ind2 = min((self.PageNum+1)*FIGURES_PER_PAGE,len(self.picPaths))
        
        self.grid._table.data = []
        for i in range(ind1,ind2):            
            try:
                width, height = get_image_size.get_image_size(self.picPaths[i])
            except get_image_size.UnknownImageFormat:
                width, height = -1, -1
                print('Warning: Failed to load figure %sn' % self.picPaths[i])
                self.totalImages-=1
                continue
            
            ratio = float(width)/float(height)
            new_height = self.COLWIDTH/ratio            
            
            if new_height < self.MAX_ROWHEIGHT:
                width = self.COLWIDTH-10
                height = self.COLWIDTH/ratio
            else:
                width = self.MAX_ROWHEIGHT*ratio
                height = self.MAX_ROWHEIGHT                
                                
            d = (str(i+1),{'video':self.picPaths[i],'dims':(width, height,ratio)})
            self.grid._table.data.append(d)
            

if __name__ == '__main__':
    app = wx.App(redirect=False)  # Error messages go to popup window
    top = TestFrame()
    top.Show()
    app.MainLoop()

