#vision/NVDAHighlighter.py
#A part of NonVisual Desktop Access (NVDA)
#This file is covered by the GNU General Public License.
#See the file COPYING for more details.
#Copyright (C) 2018 NV Access Limited, Babbage B.V., Takuya Nishimoto

"""Default highlighter based on wx."""

from . import Highlighter, CONTEXT_FOCUS, CONTEXT_NAVIGATOR, CONTEXT_CARET
import wx
import gui
import api
from ctypes.wintypes import COLORREF
import winUser
from logHandler import log
from mouseHandler import getTotalWidthAndHeightAndMinimumPosition
import cursorManager
from locationHelper import RectLTRB
import config
from collections import namedtuple

from gui.settingsDialogs import SettingsPanel

# Highlighter specific contexts
#: Context for overlapping focus and navigator objects
CONTEXT_FOCUS_NAVIGATOR = "focusNavigatorOverlap"

class ContextStyle(namedtuple("ContextStyle", ("color", "width", "style", "margin"))):
	pass

class NVDAHighlighter(Highlighter):
	name = "NVDAHighlighter"
	# Translators: Description for NVDA's built-in screen highlighter.
	description = _("NVDA Highlighter")
	supportedContexts = (CONTEXT_FOCUS, CONTEXT_NAVIGATOR, CONTEXT_CARET)
	_contextStyles = {
		CONTEXT_FOCUS: ContextStyle(wx.Colour(0x03, 0x36, 0xff, 0xff), 5, wx.PENSTYLE_SHORT_DASH, 5),
		CONTEXT_NAVIGATOR: ContextStyle(wx.Colour(0xff, 0x02, 0x66, 0xff), 5, wx.PENSTYLE_SOLID, 5),
		CONTEXT_FOCUS_NAVIGATOR: ContextStyle(wx.Colour(0x03, 0x36, 0xff, 0xff), 5, wx.PENSTYLE_SOLID, 5),
		CONTEXT_CARET: ContextStyle(wx.Colour(0xff, 0xde, 0x03, 0xff), 2, wx.PENSTYLE_SOLID, 0),
	}
	_refreshInterval = 150

	def __init__(self, *roles):
		self.window = None
		self._refreshTimer = None
		super(Highlighter, self).__init__(*roles)

	def initializeHighlighter(self):
		super(NVDAHighlighter, self).initializeHighlighter()
		self.window = HighlightWindow(self)
		self._refreshTimer = gui.NonReEntrantTimer(self.refresh)
		self._refreshTimer.Start(self._refreshInterval)

	def terminateHighlighter(self):
		if self._refreshTimer:
			self._refreshTimer.Stop()
			self._refreshTimer = None
		if self.window:
			self.window.Destroy()
			self.window = None
		super(NVDAHighlighter, self).terminateHighlighter()

	def updateContextRect(self, context, rect=None, obj=None):
		super(NVDAHighlighter, self).updateContextRect(context, rect, obj)
		self.refresh()

	def refresh(self):
		# Trigger a refresh of the highlight window, which will call onPaint
		if self.window:
			self.window.Refresh()

	def onPaint(self, event):
		window= event.GetEventObject()
		dc = wx.PaintDC(window)
		dc.SetBackground(wx.TRANSPARENT_BRUSH)
		dc.Clear()
		dc.SetBrush(wx.TRANSPARENT_BRUSH)
		contextRects = {}
		for context in self.supportedContexts:
			if not config.conf['vision'][self.name]['highlight%s' % (context[0].upper() + context[1:])]:
				continue
			rect = self.contextToRectMap.get(context)
			if not rect:
				continue
			if context == CONTEXT_CARET and not isinstance(api.getCaretObject(), cursorManager.CursorManager):
				# Non virtual carets are currently not supported
				continue
			elif context == CONTEXT_NAVIGATOR and contextRects.get(CONTEXT_FOCUS) == rect:
				# Focus is in contextRects, because rect can't be Noone here.
				contextRects.pop(CONTEXT_FOCUS)
				context = CONTEXT_FOCUS_NAVIGATOR
			contextRects[context] = rect
		for context, rect in contextRects.items():
			contextStyle = self._contextStyles[context]
			dc.SetPen(wx.ThePenList.FindOrCreatePen(contextStyle.color, contextStyle.width, contextStyle.style))
			try:
				rect = rect.expandOrShrink(contextStyle.margin).toClient(window.Handle).toLogical(window.Handle)
			except RuntimeError:
				pass
			if context == CONTEXT_CARET:
				dc.DrawLine(rect.right, rect.top, rect.right, rect.bottom)
			else:
				dc.DrawRectangle(*rect.toLTWH())

class HighlightWindow(wx.Frame):
	transparency = 0xff

	def updateLocationForDisplays(self):
		displays = [ wx.Display(i).GetGeometry() for i in xrange(wx.Display.GetCount()) ]
		screenWidth, screenHeight, minPos = getTotalWidthAndHeightAndMinimumPosition(displays)
		self.SetPosition(minPos)
		self.SetSize((screenWidth, screenHeight))

	def __init__(self, highlighter):
		super(HighlightWindow, self).__init__(gui.mainFrame, style=wx.NO_BORDER | wx.STAY_ON_TOP | wx.FULL_REPAINT_ON_RESIZE | wx.FRAME_NO_TASKBAR)
		self.updateLocationForDisplays()
		self.SetBackgroundStyle(wx.BG_STYLE_CUSTOM)
		exstyle = winUser.getExtendedWindowStyle(self.Handle) | winUser.WS_EX_LAYERED
		winUser.setExtendedWindowStyle(self.Handle, exstyle)
		winUser.SetLayeredWindowAttributes(self.Handle, 0, self.transparency, winUser.LWA_ALPHA | winUser.LWA_COLORKEY)
		self.Bind(wx.EVT_PAINT, highlighter.onPaint)
		self.ShowWithoutActivating()
		wx.CallAfter(self.Disable)

class NVDAHighlighterSettingsPanel(SettingsPanel):

	def makeSettings(self, sizer):
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=sizer)
		# Translators: This is the label for a checkbox in the
		# default highlighter settings panel to enable highlighting the focus.
		self.highlightFocusCheckBox=sHelper.addItem(wx.CheckBox(self,label=_("Highlight &focus")))
		self.highlightFocusCheckBox.SetValue(config.conf['vision'][NVDAHighlighter.name]["highlightFocus"])
		# Translators: This is the label for a checkbox in the
		# default highlighter settings panel to enable highlighting the navigator object.
		self.highlightNavigatorObjCheckBox=sHelper.addItem(wx.CheckBox(self,label=_("Highlight &navigator object")))
		self.highlightNavigatorObjCheckBox.SetValue(config.conf['vision'][NVDAHighlighter.name]["highlightNavigatorObj"])
		# Translators: This is the label for a checkbox in the
		# default highlighter settings panel to enable highlighting the virtual caret (such as in browse mode).
		self.highlightCaretCheckBox=sHelper.addItem(wx.CheckBox(self,label=_("Follow &browse mode caret")))
		self.highlightCaretCheckBox.SetValue(config.conf['vision'][NVDAHighlighter.name]["highlightCaret"])

	def onSave(self):
		config.conf['vision'][NVDAHighlighter.name]["highlightFocus"]=self.highlightFocusCheckBox.IsChecked()
		config.conf['vision'][NVDAHighlighter.name]["highlightNavigatorObj"]=self.highlightNavigatorObjCheckBox.IsChecked()
		config.conf['vision'][NVDAHighlighter.name]["highlightCaret"]=self.highlightCaretCheckBox.IsChecked()

NVDAHighlighter.guiPanelCls = NVDAHighlighterSettingsPanel