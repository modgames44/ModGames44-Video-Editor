"""Contrato funcional del controlador de layouts, mediante dobles de Qt.

Esto NO sustituye una prueba visual con PySide6 en Windows.
"""
import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import patch


class StubDock:
    def __init__(self, name):
        self.name=name
        self.hidden=True
        self.floating=False
        self.parent=None
        self.visibility=[]

    def hide(self):
        self.hidden=True
        self.visibility.append(False)

    def show(self):
        self.hidden=False
        self.visibility.append(True)

    def setFloating(self, value):
        self.floating=value


class StubWindow:
    def __init__(self):
        self.log=[]
        self.saved_count=0

    def width(self):return 1536
    def height(self):return 900
    def removeDockWidget(self,d):self.log.append(('remove',d.name))
    def addDockWidget(self,area,d):self.log.append(('add',d.name))
    def splitDockWidget(self,a,b,orientation):self.log.append(('split',a.name,b.name))
    def tabifyDockWidget(self,a,b):self.log.append(('tab',a.name,b.name))
    def saveState(self,version):
        self.saved_count+=1
        return f'state:{self.saved_count}'
    def restoreState(self,state,version):
        self.log.append(('restore',state))
        return True
    def resizeDocks(self,docks,sizes,orientation):pass


class StubSettings:
    def __init__(self):self.data={}
    def value(self,key,default=None):return self.data.get(key,default)
    def setValue(self,key,value):self.data[key]=value
    def remove(self,key):self.data.pop(key,None)


class StubSignal:
    def __init__(self):self.seen=[]
    def emit(self,v):self.seen.append(v)


class StubQt:
    class DockWidgetArea:
        LeftDockWidgetArea=1
        RightDockWidgetArea=2
        BottomDockWidgetArea=3
    class Orientation:
        Horizontal=4
        Vertical=5


class WorkspaceManagerTests(unittest.TestCase):
    def setUp(self):
        qtcore=types.ModuleType('PySide6.QtCore')
        qtcore.QObject=type('QObject',(object,),{'__init__':lambda self,*args:None})
        qtcore.Signal=lambda *args:StubSignal()
        qtcore.Qt=StubQt
        qtcore.QTimer=types.SimpleNamespace(singleShot=lambda delay,fn:fn())
        pyside=types.ModuleType('PySide6')
        self.patcher=patch.dict(sys.modules,{'PySide6':pyside,'PySide6.QtCore':qtcore})
        self.patcher.start()
        path=pathlib.Path(__file__).parents[1] / 'ui' / 'workspace_manager.py'
        spec=importlib.util.spec_from_file_location('_test_manager',path)
        mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.Manager=mod.WorkspaceManager
        names=('Proyecto','Herramientas','Efectos (futuro)','Timeline','Audio Meter','Propiedades','Asistente IA')
        self.docks={name:StubDock(name) for name in names}
        self.window=StubWindow()
        self.settings=StubSettings()
        self.manager=self.Manager(self.window,self.docks,self.settings)

    def tearDown(self):self.patcher.stop()

    def test_switch_preserves_widgets_and_each_workspace(self):
        self.manager.activate('neon')
        self.assertEqual(self.manager.active,'neon')
        self.assertFalse(self.docks['Propiedades'].hidden)
        self.assertFalse(self.docks['Efectos (futuro)'].hidden)
        self.manager.activate('studio')
        self.assertFalse(self.docks['Propiedades'].hidden)
        self.assertFalse(self.docks['Proyecto'].hidden)
        self.assertIn(self.manager._state_key('neon'),self.settings.data)
        self.manager.activate('neon')
        self.assertEqual(self.settings.data['workspaces/active'],'neon')
        self.assertIn(('restore','state:1'),self.window.log)

    def test_reset_does_not_destroy_project(self):
        self.manager.activate('studio')
        self.manager.save_active()
        self.assertIn(self.manager._state_key('studio'),self.settings.data)
        self.manager.reset_active()
        self.assertNotIn(self.manager._state_key('studio'),self.settings.data)
        self.assertFalse(self.docks['Propiedades'].hidden)


if __name__=='__main__':unittest.main()
