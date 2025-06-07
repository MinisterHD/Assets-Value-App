CONFIG      += plugin debug_and_release
TARGET      = $$qtLibraryTarget(menuplugin)
TEMPLATE    = lib

HEADERS     = menuplugin.h
SOURCES     = menuplugin.cpp
RESOURCES   = icons.qrc
LIBS        += -L. 

QT += designer

target.path = $$[QT_INSTALL_PLUGINS]/designer
INSTALLS    += target

include(menu.pri)
