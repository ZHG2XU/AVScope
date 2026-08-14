cmake_minimum_required(VERSION 3.24)

project(AVScopeQt VERSION 0.2.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)

find_package(Qt6 6.8 REQUIRED COMPONENTS Core Gui Widgets Multimedia)

qt_add_executable(AVScopeQt WIN32
    src/main.cpp
    src/MainWindow.cpp
    src/MainWindow.h
    src/MediaPreviewWidget.cpp
    src/MediaPreviewWidget.h
    src/TimelineWidget.cpp
    src/TimelineWidget.h
    src/HexCompareWidget.cpp
    src/HexCompareWidget.h
    src/HexView.cpp
    src/HexView.h
    resources/avscope.qrc
    resources/avscope.rc
)

target_link_libraries(AVScopeQt PRIVATE Qt6::Core Qt6::Gui Qt6::Widgets Qt6::Multimedia)
target_compile_definitions(AVScopeQt PRIVATE AVSCOPE_VERSION="${PROJECT_VERSION}")

set_target_properties(AVScopeQt PROPERTIES
    OUTPUT_NAME "AVScope"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)
