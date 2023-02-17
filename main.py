import sys
import os
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QApplication, QMainWindow, QMenuBar, QPushButton
from PyQt5.QtWidgets import *
from PyQt5.uic import loadUi
import psutil
import threading
import time
from MQTT import Client



c : Client = 0
connect = 0
message_thread : threading.Thread = 0
running = 0



class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow,self).__init__()
        loadUi("connect.ui",self)

        self.actionPublish.triggered.connect(self.setPublish)
        self.actionSubscribe.triggered.connect(self.setSubscribe)
        
        self.connectButton.clicked.connect(self.connect)
        self.disconnectButton.clicked.connect(self.disconnect)

        app.aboutToQuit.connect(self.closeEvent)
        

    def connect(self):
        global c
        global connect
        time = self.keepAliveTime.value()
        c = Client(self.BrokerAddrField.text(), 1883, keep_alive=time, username=self.usernameField.text(), password=self.passwordField.text())
        c.connect_socket()

        if(c.connection == 1):
            c.connect( will_topic= self.willTopic.text(),will_payload=self.willMsg.text())
        if(c.connection == 1):
            connect = 1
        else:
            connect = 0
        self.messageField.clear()
        if(connect):
            self.messageField.addItem("Connection established!")
        else:
            self.messageField.addItem("Connection could't be established!")     



    def disconnect(self):
        global c
        global connect, running
        if(connect == 1):
            c.disconnect(False)
            c.running = 0
            connect = 0
            running = 0
            self.messageField.clear()
            self.messageField.addItem("Client disconnected!") 


        
    def setPublish(self):
        widget.setCurrentIndex(1)
    def setSubscribe(self):
        widget.setCurrentIndex(2)

    def closeEvent(self):
        global c
        print('Close button pressed')
        self.disconnect()
        os._exit(0)


class PublishScreen(QMainWindow):
    def __init__(self):
        super(PublishScreen,self).__init__()
        loadUi("publish.ui",self)
        self.actionConnect.triggered.connect(self.setConnect)
        self.actionSubscribe.triggered.connect(self.setSubscribe)
        self.publishButton.clicked.connect(self.publish)

        app.aboutToQuit.connect(self.closeEvent)

    def publish(self):
        global c, connect
        vals = []
        if(connect == 1):
            if(self.cpu.isChecked()):
                cpu = psutil.cpu_percent()
                vals.append(("CPU", str(cpu)))
            if(self.ram.isChecked()):
                ram = psutil.virtual_memory()
                vals.append(("RAM", str(ram)))
            if(self.battery.isChecked()):
                battery=psutil.sensors_battery()
                vals.append(("BATTERY", str(battery)))

            print(vals)
            for val in vals:
                threading.Thread(target=c.publish, args=(val[0], val[1], int(self.qos.currentText()))).start()
        
    def setConnect(self):
        widget.setCurrentIndex(0)
    def setSubscribe(self):
        widget.setCurrentIndex(2)

    def closeEvent(self):
        global c
        print('Close button pressed')
        MainWindow.disconnect(mainwindow)
        os._exit()

class SubscribeScreen(QMainWindow):
   # messageList = []
    timer: threading.Timer = 0
    def __init__(self):
        super(SubscribeScreen,self).__init__()
        loadUi("subscribe.ui",self)
        self.actionPublish.triggered.connect(self.setPublish)
        self.actionConnect.triggered.connect(self.setConnect)

        self.subscribeButton.clicked.connect(self.subscribe)
        self.unsubscribeButton.clicked.connect(self.unsubscribe)

        app.aboutToQuit.connect(self.closeEvent)
            

    def subscribe(self):
        global c, connect, running
        if(connect == 1):
            if(self.cpu.isChecked()):
                c.subscribe("testtopic/topic_mehdi")
            if(self.ram.isChecked()):
                c.subscribe("testtopic/SwiftOnSecurity")
            if(self.battery.isChecked()):
                c.subscribe("testtopic/EBO")
            # if(self.cpu.isChecked()):
            #     c.subscribe("CPU")
            # if(self.ram.isChecked()):
            #     c.subscribe("RAM")
            # if(self.battery.isChecked()):
            #     c.subscribe("BATTERY")
            if(running == 0):
                running = 1
                message_thread = threading.Thread(target=self.showMessages)
                message_thread.start()

                print("RUNning:") 

    
    def unsubscribe(self):
        global c, connect
        if(connect == 1):
            if(self.cpu.isChecked()):
                c.unsubscribe("testtopic/topic_mehdi")
            if(self.ram.isChecked()):
                c.unsubscribe("testtopic/SwiftOnSecurity")
            if(self.battery.isChecked()):
                c.unsubscribe("testtopic/EBO")
            # if(self.cpu.isChecked()):
            #     c.unsubscribe("CPU")
            # if(self.ram.isChecked()):
            #     c.unsubscribe("RAM")
            # if(self.battery.isChecked()):
            #     c.unsubscribe("BATTERY")

    def setConnect(self):
        widget.setCurrentIndex(0)
    def setPublish(self):
        widget.setCurrentIndex(1)
    
    def closeEvent(self):
        global c
        print('Close button pressed')
        MainWindow.disconnect(mainwindow)
        os._exit(0)

    def showMessages(self):
        global c, connect, running
        while(running):
            time.sleep(3)
            print("EHEHE: ")
            if(connect == 1):
                self.messageField.clear()
                print("AAAAAA: " + str(c.publishedPackets))
                for i in range(0, len(c.publishedPackets)):
                    self.messageField.addItem("Topic: " + c.publishedPackets[i][0].decode('utf-8') + ", Message: " + c.publishedPackets[i][1].decode('utf-8'))
                c.publishedPackets.clear()
                self.messageField.show()



if __name__ == "__main__":
    app=QApplication(sys.argv)
    
    mainwindow=MainWindow()
    publishScreen = PublishScreen()
    subscribeScreen = SubscribeScreen()
    

    widget=QtWidgets.QStackedWidget()

    widget.addWidget(mainwindow)
    widget.addWidget(publishScreen)
    widget.addWidget(subscribeScreen)

    widget.setWindowTitle("MQTT Protocol v5")
    widget.setFixedWidth(400)
    widget.setFixedHeight(300)
    widget.show()


    sys.exit(app.exec_())