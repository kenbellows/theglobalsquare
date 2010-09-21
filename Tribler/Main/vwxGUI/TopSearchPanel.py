# generated by wx.Glade 0.6.3 on Thu Feb 05 15:42:50 2009
# 
# Arno: please edit TopSearchPanel.xrc in some XRC editor, then generate
# code for it using wxGlade (single python file mode), and copy the
# relevant parts from it into this file, see "MAINLY GENERATED" line below.
#
# We need this procedure as there is a bug in wxPython 2.8.x on Win32 that
# cause the painting/fitting of the panel to fail. All elements wind up in
# the topleft corner. This is a wx bug as it also happens in XRCED when you
# display the panel twice.
#

from GuiUtility import GUIUtility
from Tribler.Main.Utility.utility import Utility
from Tribler.__init__ import LIBRARYNAME
from bgPanel import bgPanel
from tribler_topButton import *
from traceback import print_exc
from wx.lib.buttons import GenBitmapButton as BitmapButton

import math
import os
import sys
import time
import wx
import wx.xrc as xrc

# begin wx.Glade: extracode
# end wx.Glade


wx.SystemOptions_SetOption("msw.remap", "1")

DEBUG = False

class TopSearchPanel(bgPanel):
    def __init__(self, *args, **kwds):
        if DEBUG:
            print >> sys.stderr , "TopSearchPanel: __init__"
        bgPanel.__init__(self, *args, **kwds)
        self.init_ready = False
        self.guiUtility = GUIUtility.getInstance()
        self.utility = self.guiUtility.utility 
        self.installdir = self.utility.getPath()
        
        self.buttonsBackgroundColourSelected = wx.Colour(235, 233, 228)
        self.buttonsBackgroundColour = wx.Colour(193, 188, 177)
        self.buttonsForegroundColour = wx.BLACK
     
    def OnSearchKeyDown(self, event):
        if DEBUG:
            print >> sys.stderr, "TopSearchPanel: OnSearchKeyDown"
            
        if self.searchField.GetValue().strip() == '':
            self.Notify('Please enter a search term', wx.ART_INFORMATION)
        else:
            self.ag.Show()
            self.go.GetContainingSizer().Layout()
            self.ag.Play()
                
            # Timer to stop animation after 10 seconds. No results will come 
            # in after that
            self.guiUtility.frame.guiserver.add_task(lambda:wx.CallAfter(self.HideAnimation), 10.0)
            
            if not self.results.IsEnabled():
                self.results.Enable()
                      
            self.selectTab('results')
            self.results.SetValue(True)

            # Arno: delay actual search so the painting is faster.
            wx.CallAfter(self.guiUtility.dosearch)

    def OnResults(self, event):
        if self.guiUtility.guiPage != 'search_results':
            self.selectTab('results')
            #Need to use callafter, to allow list to get focus
            wx.CallAfter(self.guiUtility.ShowPage, 'search_results')
        else: #Absorb event to prevent untoggle
            event.Skip(False)

    def OnChannels(self, event):
        if self.guiUtility.guiPage not in ['channels', 'selectedchannel', 'mychannel']:
            self.selectTab('channels')
            wx.CallAfter(self.guiUtility.ShowPage, 'channels')
        else: #Absorb event to prevent untoggle
            event.Skip(False)
   
    def OnSettings(self, event):
        wx.CallAfter(self.guiUtility.ShowPage, 'settings')
        event.Skip(False)

    def OnLibrary(self, event):
        if self.guiUtility.guiPage != 'my_files':
            self.selectTab('my_files')
            wx.CallAfter(self.guiUtility.ShowPage, 'my_files')
        else: #Absorb event to prevent untoggle
            event.Skip(False)

    def selectTab(self, tab):
        self.results.SetValue(tab == 'results')
        self.channels.SetValue(tab == 'channels')
        self.settings.SetValue(tab == 'settings')
        self.my_files.SetValue(tab == 'my_files')
        
    def autocomplete(self):
        """appends the most frequent completion according to
           buddycast clicklog to the current input.
           sets the appended characters to "selected" such that they are
           automatically deleted as the user continues typing"""
        input = self.searchField.GetValue()
        terms = input.split(" ")
        # only autocomplete if the last term in the input contains more than one character
        if len(terms[-1]) > 1:
            completion = self.complete(terms[-1])
            if completion:
                l = len(input)
                self.searchField.SetValue(input + completion)
                self.searchField.SetSelection(l, l + len(completion))
                
    def complete(self, term):
        """autocompletes term."""
        completion = self.utility.session.open_dbhandler(NTFY_TERM).getTermsStartingWith(term, num=1)
        if completion:
            return completion[0][len(term):]
        # boudewijn: may only return unicode compatible strings. While
        # "" is unicode compatible it is better to return u"" to
        # indicate that it must be unicode compatible.
        return u""

    def SearchFocus(self):
        self.searchField.SetFocus()
        self.searchField.SelectAll()

    def Bitmap(self, path, type):
        namelist = path.split("/")
        path = os.path.join(self.installdir, LIBRARYNAME, "Main", "vwxGUI", *namelist)
        return wx.Bitmap(path, type)
        
    def _PostInit(self):
        if DEBUG:
            print >> sys.stderr, "TopSearchPanel: OnCreate"
            
        bgPanel._PostInit(self)
        if sys.platform == 'linux2': #bug in linux for searchctrl, focus does not hide search text + text stays grey
            self.searchField = wx.TextCtrl(self, -1, "", style=wx.TE_PROCESS_ENTER)
        else:
            self.searchField = wx.SearchCtrl(self, -1, "", style=wx.TE_PROCESS_ENTER)
        
        self.go = tribler_topButton(self,-1,name = 'Search_new')
        self.channels = wx.ToggleButton(self, -1, label='Channels', name="Channels")
        self.settings = wx.ToggleButton(self, -1, label='Settings', name="Settings")
        self.my_files = wx.ToggleButton(self, -1, label='Library', name="My Files")
        self.results = wx.ToggleButton(self, -1, label='Results', name="Results")
        self.results.Disable()

        if sys.platform == 'win32':
            self.files_friends = wx.StaticBitmap(self, -1, self.Bitmap("images/search_files_channels.png", wx.BITMAP_TYPE_ANY))
            self.tribler_logo2 = wx.StaticBitmap(self, -1, self.Bitmap("images/logo4video2_win.png", wx.BITMAP_TYPE_ANY))
        else:    
            self.files_friends = wx.StaticText(self, -1, "Search Files or Channels") 
            self.tribler_logo2 = wx.StaticBitmap(self, -1, self.Bitmap("images/logo4video2.png", wx.BITMAP_TYPE_ANY))
        
        self.__set_properties()
        self.__do_layout()

        # OUR CODE
        self.custom_init()
        self.init_ready = True
        
        self.Layout()
        
    def __set_properties(self):
        self.SetBackgroundColour(wx.Colour(255, 255, 255))
        
        self.searchField.SetMinSize((400, -1))
        self.searchField.SetFocus()
        
        self.go.SetMinSize((50, 24))
        
        if sys.platform == 'linux2':
            self.files_friends.SetFont(wx.Font(8, wx.SWISS, wx.NORMAL, wx.BOLD, 0, "Nimbus Sans L"))
                
        elif sys.platform == 'darwin': # mac
            self.files_friends.SetFont(wx.Font(8, wx.SWISS, wx.NORMAL, wx.BOLD, 0, ""))


    def __do_layout(self):
        mainSizer = wx.BoxSizer(wx.HORIZONTAL)
        
        #Add searchbox etc.
        searchSizer = wx.BoxSizer(wx.VERTICAL)

        #Search for files or channels label
        searchSizer.Add(self.files_friends, 0, wx.TOP, 20) 
        if sys.platform == 'win32': #platform specific spacer
            searchSizer.AddSpacer((0, 6))
        else:
            searchSizer.AddSpacer((0, 3))
        
        searchBoxSizer = wx.BoxSizer(wx.HORIZONTAL)
        searchBoxSizer.Add(self.searchField, 1, wx.TOP, 1) #add searchbox
        searchBoxSizer.Add(self.go, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5) #add searchbutton

        if sys.platform == 'darwin' or sys.platform == 'win32':
            ag_fname = os.path.join(self.utility.getPath(), LIBRARYNAME, 'Main', 'vwxGUI', 'images', 'search_new_windows.gif')
        else:
            ag_fname = os.path.join(self.utility.getPath(), LIBRARYNAME, 'Main', 'vwxGUI', 'images', 'search_new.gif')
        self.ag = wx.animate.GIFAnimationCtrl(self, -1, ag_fname)
        searchBoxSizer.Add(self.ag, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RESERVE_SPACE_EVEN_IF_HIDDEN, 3)
        searchSizer.Add(searchBoxSizer, 0, wx.EXPAND)
        
        #finished searchSizer, add to mainSizer
        mainSizer.Add(searchSizer, 0, wx.LEFT, 10)
        
        #niels: add strechingspacer, all controls added before 
        #this spacer will be aligned to the left of the screen
        #all controls added after, will be to the right
        mainSizer.AddStretchSpacer()
        
        #add buttons
        self.buttonSizer = wx.BoxSizer(wx.VERTICAL)
        
        #add buttons horizontally
        buttonBoxSizer = wx.BoxSizer(wx.HORIZONTAL)
        buttonBoxSizer.Add(self.results, 0, wx.RIGHT, 5)
        buttonBoxSizer.Add(self.channels, 0, wx.RIGHT, 5)
        buttonBoxSizer.Add(self.settings, 0, wx.RIGHT, 5)
        buttonBoxSizer.Add(self.my_files)
        
        self.buttonSizer.Add(buttonBoxSizer, 0, wx.TOP, 3)
        
        self.notifyPanel = wx.Panel(self)
        self.notifyPanel.SetBackgroundColour("yellow")
        self.notifyIcon = wx.StaticBitmap(self.notifyPanel, -1, wx.ArtProvider.GetBitmap(wx.ART_INFORMATION))
        self.notify = wx.StaticText(self.notifyPanel)
        
        notifyS = wx.BoxSizer(wx.HORIZONTAL)
        notifyS.Add(self.notifyIcon, 0, wx.LEFT | wx.TOP | wx.BOTTOM, 5)
        notifyS.Add(self.notify, 1, wx.LEFT | wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 5)
        self.notifyPanel.SetSizer(notifyS)
        
        self.buttonSizer.Add(self.notifyPanel, 0, wx.ALIGN_RIGHT | wx.TOP, 5)
        mainSizer.Add(self.buttonSizer)
        
        mainSizer.AddSpacer((15, 0))
        
        mainSizer.Add(self.tribler_logo2, 0, wx.TOP, 3)
        mainSizer.AddSpacer((10, 0))
        self.SetSizer(mainSizer)
        
    def custom_init(self):
        hide_names = [self.ag, self.notifyPanel]
        for name in hide_names:
            name.Hide()
        
        # binding events  
        self.searchField.Bind(wx.EVT_TEXT_ENTER, self.OnSearchKeyDown)
        self.searchField.Bind(wx.EVT_SEARCHCTRL_SEARCH_BTN, self.OnSearchKeyDown)
        self.go.Bind(wx.EVT_LEFT_UP, self.OnSearchKeyDown)
        self.results.Bind(wx.EVT_LEFT_UP, self.OnResults)
        self.settings.Bind(wx.EVT_LEFT_UP, self.OnSettings)
        self.my_files.Bind(wx.EVT_LEFT_UP, self.OnLibrary)
        self.channels.Bind(wx.EVT_LEFT_UP, self.OnChannels)     
        
    def Notify(self, msg, icon= -1):
        self.notify.SetLabel(msg)
        self.notify.SetSize(self.notify.GetBestSize())
        
        if icon != -1:
            self.notifyIcon.Show()
            self.notifyIcon.SetBitmap(wx.ArtProvider.GetBitmap(icon))
        else:
            self.notifyIcon.Hide()
        
        self.Freeze()
        self.notifyPanel.Show()
        #NotifyLabel size changed, thus call Layout
        self.buttonSizer.Layout()
        self.guiUtility.frame.guiserver.add_task(lambda:wx.CallAfter(self.HideNotify), 5.0)
        self.Thaw()

    def HideNotify(self):
        self.notifyPanel.Hide()
        
    def HideAnimation(self):
        self.ag.Stop()
        self.ag.Hide()
