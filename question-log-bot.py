"""
Based on the twisted example IRC log bot - logs a channel's events to a file.

See LICENSE for details
"""


# twisted imports
from twisted.enterprise import adbapi
from twisted.words.protocols import irc
from twisted.internet import reactor, protocol
from twisted.python import log

# system imports
import os
import sys
import time


class MessageLogger:
    """
    An independent logger class (because separation of application
    and protocol logic is a good thing).
    """
    def __init__(self, file):
        self.file = file

    def log(self, message):
        """Write a message to the file."""
        timestamp = time.strftime("[%H:%M:%S]", time.localtime(time.time()))
        self.file.write('%s %s\n' % (timestamp, message))
        self.file.flush()

    def close(self):
        self.file.close()


class LogBot(irc.IRCClient):
    """A logging IRC bot."""

    nickname = "pappu"

    def connectionMade(self):
        irc.IRCClient.connectionMade(self)
        self.logger = MessageLogger(open(self.factory.filename, "a"))
        print ("[connected at %s]" % time.asctime(time.localtime(time.time())))

    def connectionLost(self, reason):
        irc.IRCClient.connectionLost(self, reason)
        print ("[disconnected at %s]" % time.asctime(time.localtime(time.time())))
        self.logger.close()

    # callbacks for events

    def signedOn(self):
        """Called when bot has succesfully signed on to server."""
        self.join(self.factory.chat_channel)
        self.join(self.factory.main_channel)

    def joined(self, channel):
        """This will get called when the bot joins the channel."""
        print ("[I have joined %s]" % channel)

    def privmsg(self, user, channel, msg):
        """This will get called when the bot receives a message."""
        nick = user.split('!', 1)[0]
        if channel == self.factory.main_channel:
            self.logger.log("<%s> %s" % (nick, msg))

        # Check to see if they're sending me a private message
        if channel == self.nickname:
            return

        # If message is a question, save to database and insert into factory
        # question dictionary
        if msg.startswith("QUESTION:") and channel == self.factory.chat_channel:
            question = msg.split(':')[1].strip()
            self.factory.dbpool.runQuery(self.factory.insert_query,
                                        (int(time.time()), nick, question, 0))
            adict = {}
            adict['nick'] = nick
            adict['question'] = question
            self.factory.questions.append(adict)
        elif channel == self.factory.main_channel and nick in self.factory.admins and msg == "@next":
            send_msg = ""
            if self.factory.questions == []:
                send_msg = "Queue is empty!"
            else:
                question = self.factory.questions.pop(0)
                send_msg = question["nick"] + " asked \"" + question['question'] + "\""
                self.factory.dbpool.runOperation(self.factory.update_query, (question["nick"], question["question"]))

            self.msg(self.factory.main_channel, send_msg)
            self.logger.log("<%s> %s" % ("pappu", send_msg))

    def action(self, user, channel, msg):
        """This will get called when the bot sees someone do an action."""
        return

    # irc callbacks

    def irc_NICK(self, prefix, params):
        """Called when an IRC user changes their nickname."""
        return

    # For fun, override the method that determines how a nickname is changed on
    # collisions. The default method appends an underscore.
    def alterCollidedNick(self, nickname):
        """
        Generate an altered version of a nickname that caused a collision in an
        effort to create an unused related name for subsequent registration.
        """
        return nickname + '^'


class LogBotFactory(protocol.ClientFactory):
    """A factory for LogBots.

    A new protocol instance will be created each time we connect to the server.
    """

    def __init__(self):
        self.admins = ["bithin", "dnivra", "seshagiri"]
        self.chat_channel = "#inctf-chat"
        self.database_file = os.path.join(os.path.dirname(__file__), 'data.db')
        self.dbpool = adbapi.ConnectionPool("sqlite3", self.database_file)
        self.filename = "inctf-logs.txt"
        self.insert_query = "INSERT INTO questions(timestamp, nick, question, answered) values(?, ?, ?, ?)"
        self.main_channel = "#inctf"
        self.questions = []
        self.retrieve = "SELECT nick, question from questions where answered = 0 order by timestamp"
        self.update_query = "UPDATE questions set answered = 1 where nick = ? and question = ?"
        query = self.dbpool.runQuery(self.retrieve)
        query.addCallbacks(self.retr_success, self.retr_failure)

    def __del__(self):
        self.dbpool.close()

    def buildProtocol(self, addr):
        p = LogBot()
        p.factory = self
        return p

    def clientConnectionLost(self, connector, reason):
        """If we get disconnected, reconnect to server."""
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        print "connection failed:", reason
        reactor.stop()

    def retr_success(self, rows):
        for row in rows:
            adict = {}
            adict['nick'] = str(row[0])
            adict['question'] = str(row[1])
            self.questions.append(adict)

        return

    def retr_failure(self, err):
        print(err)


if __name__ == '__main__':
    # initialize logging
    log.startLogging(sys.stdout)

    # create factory protocol and application
    f = LogBotFactory()

    # connect factory to this host and port
    reactor.connectTCP("irc.freenode.net", 6667, f)

    # run bot
    reactor.run()
