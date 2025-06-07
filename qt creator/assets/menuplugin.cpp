#include "menuplugin.h"
#include "menu.h"

#include <QtPlugin>

menuPlugin::menuPlugin(QObject *parent)
    : QObject(parent)
{}

void menuPlugin::initialize(QDesignerFormEditorInterface * /* core */)
{
    if (m_initialized)
        return;

    // Add extension registrations, etc. here

    m_initialized = true;
}

bool menuPlugin::isInitialized() const
{
    return m_initialized;
}

QWidget *menuPlugin::createWidget(QWidget *parent)
{
    return new menu(parent);
}

QString menuPlugin::name() const
{
    return QLatin1String("menu");
}

QString menuPlugin::group() const
{
    return QLatin1String("");
}

QIcon menuPlugin::icon() const
{
    return QIcon();
}

QString menuPlugin::toolTip() const
{
    return QLatin1String("");
}

QString menuPlugin::whatsThis() const
{
    return QLatin1String("");
}

bool menuPlugin::isContainer() const
{
    return false;
}

QString menuPlugin::domXml() const
{
    return QLatin1String(R"(<widget class="menu" name="menu">
</widget>)");
}

QString menuPlugin::includeFile() const
{
    return QLatin1String("menu.h");
}
