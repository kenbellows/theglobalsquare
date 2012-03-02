import wx
import wx.html

def main():
  
  tgsApp = wx.App()
  
  #tgsMainWindow = wx.Frame(None, -1, 'Test')
  #tgsMainWindow.Show()
  
  tgsHTMLWindow = wx.html.HtmlWindow(None, -1, size=(300,200), name='Test')
  
  wx.CallAfter(tgsHTMLWindow.LoadPage, "test.html")
  
  tgsHTMLWindow.Show()
 

  tgsApp.MainLoop()
  
  
if __name__ == "__main__":
  main()

