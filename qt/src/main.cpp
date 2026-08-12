#include "MainWindow.h"

#include <QApplication>
#include <QFont>
#include <QDir>
#include <QFileInfo>
#include <QStyleFactory>
#include <QTimer>

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    app.setApplicationName("AVScope");
    app.setApplicationDisplayName("AVScope");
    app.setOrganizationName("AVScope");
    app.setApplicationVersion(AVSCOPE_VERSION);
    app.setStyle(QStyleFactory::create("Fusion"));

    QFont font("Microsoft YaHei UI", 9);
    font.setStyleHint(QFont::SansSerif);
    app.setFont(font);

    MainWindow window;
    window.show();
    bool widthOk = false;
    bool heightOk = false;
    const int requestedWidth = qEnvironmentVariableIntValue("AVSCOPE_WINDOW_WIDTH", &widthOk);
    const int requestedHeight = qEnvironmentVariableIntValue("AVSCOPE_WINDOW_HEIGHT", &heightOk);
    if (widthOk && heightOk)
        window.resize(requestedWidth, requestedHeight);
    if (argc > 1) {
        window.openPath(QString::fromLocal8Bit(argv[1]));
    }
    const QString screenshotPath = qEnvironmentVariable("AVSCOPE_SCREENSHOT");
    if (!screenshotPath.isEmpty()) {
        QTimer::singleShot(3500, &window, [&app, &window, screenshotPath] {
            QDir().mkpath(QFileInfo(screenshotPath).absolutePath());
            window.grab().save(screenshotPath);
            app.quit();
        });
    }
    return app.exec();
}
