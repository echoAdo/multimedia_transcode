#encoding=utf-8

import string
import os
import os.path
import platform
import subprocess
from xml.etree import ElementTree as ET

def runShellCommand(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT):
    """run linux shell command, return result or error"""
    p = subprocess.Popen(cmd, stdout=stdout, stderr=stderr, shell=True)
    returnCode = p.wait()
    result = p.communicate()
    if returnCode:
        print 'subProcess execute failed (%s) ' % cmd
        return None

    return result[0]

class FileProcess:
    def __init__(self):
        self.srcDirectory = "input"
        self.dstDirectory = "output"
        self.srcFile = ''
        self.cmdPath = ''

        if not os.path.exists(self.dstDirectory):
            os.makedirs(self.dstDirectory)

        self.ffprobePrefix = "ffprobe -v error -show_entries format -select_streams v -show_entries stream -of xml -i "

    def browserDirectory(self):
        system = platform.system();
        print "Current system is :" + system

        if system == "Windows":
            self.cmdPath = os.getcwd() + os.sep + "winFFmpeg" + os.sep
        elif system =="Darwin" or system == "Linux":
            pass

        failedFiles = []
        list_dirs = os.walk(self.srcDirectory)
        for root, dirs, files in list_dirs:
            for f in files:
                self.srcFile = os.path.join(root, f)
                print f;
                ffprobeCmd = self.cmdPath + self.ffprobePrefix + self.srcFile
                xml = runShellCommand(ffprobeCmd)
                if xml is None:
                    failedFiles.append(self.srcFile + " ffprob")
                    continue

                srcFileInfo = MediaXMlParser().parser(xml)

                ffmpegCmd = self.buildFFmpegCommand(srcFileInfo)
                transcodeStatus = runShellCommand(ffmpegCmd)
                if transcodeStatus is None:
                    failedFiles.append(self.srcFile  + " ffmpeg")

        """Save transcode failed file name"""
        fileHandle = open(self.dstDirectory + os.sep +'transcodeResult.txt', 'a')
        fileHandle.write('\r\n **********************************************\r\n')
        for item in failedFiles:
            fileHandle.write(item + '\r\n');
            print item
        fileHandle.close()

        '''Remove unused file that generate in ffmpeg pass 1'''
        os.remove('ffmpeg2pass-0.log')
        os.remove('ffmpeg2pass-0.log.mbtree')

    def buildFFmpegCommand(self, fileInfo):
        '''buidFFmpegCommand'''

        fileName = self.srcFile.split(os.sep)[-1]
        dstFile = self.dstDirectory + os.sep + fileName[0:fileName.rfind('.')] + '.mp4'

        """IDR frame interval"""
        vDuration = int(string.atof(fileInfo.get('gDuration')))
        if vDuration <= 10 : interval = 1
        elif vDuration > 10 and vDuration <= 30 : interval = 3
        else: interval = 0

        if interval > 0: vIDRFrameInter = '-force_key_frames "expr:gte(t,n_forced*%s)"' % interval
        else: vIDRFrameInter = ''

        """ Resolution: 
            width/height > 16:10, eg:16:9, 16:10, 5:3 -> 856x480 
            other width/height < 16:10                -> 640x480
        """
        width   = fileInfo.get('vWidth')
        height  = fileInfo.get('vHeight')
        if string.atoi(width) <= 640 or string.atoi(height) <= 480:
            vResolution = width + "x" + height
        else :
            aspectRatio = float(width) / float(height)
            if aspectRatio >= 1.6:
                vResolution = '856' + 'x' + '480'
            else:
                vResolution = '640' + 'x' + '480'
            print  aspectRatio

        '''vFrameRate: > 25fps -> 25fps, <= 25fps  --> origin fps'''
        ele = fileInfo.get('vFrameRate').split('/')
        frameRate = string.atof(ele[0]) / string.atof(ele[1])
        if frameRate > 25: vFrameRate = 25
        else: vFrameRate = round(frameRate,3)

        '''BitRate: TotalBitRate(1000k) = vBR(872k) +aBR(128k)'''
        ABR_VBV = '-b:v 872k -maxrate 872k -bufsize 1600k'

        system = platform.system();
        if system == "Windows":
            cmdJoinSep = ' NUL & '
        elif system == "Darwin" or system == "Linux":
            cmdJoinSep = " /dev/null && "

        # ffmpegCmd = 'ffmpeg -i backup235.ts -c:v libx264 -b:v 1M -maxrate 1M -bufsize 2M -pass 1 -f mp4 /dev/null -y && ' \
        #             'ffmpeg -i backup235.ts -c:v libx264 -b:v 1M -maxrate 1M -bufsize 2M -pass 2 twopass.mp4 -y'

        ffmpegPass1 = '%sffmpeg -i %s -pass 1 -y -v error -c:v libx264  %s -s:v %s -r %s -c:a aac -ar 44100 -ac 2 -ab 128k %s -f mp4 ' \
                      % (self.cmdPath, self.srcFile, vIDRFrameInter, vResolution, vFrameRate, ABR_VBV)
        ffmpegPass2 = '%sffmpeg -i %s -pass 2 -y -v error -c:v libx264  %s -s:v %s -r %s -c:a aac -ar 44100 -ac 2 -ab 128k %s %s' \
                      % (self.cmdPath, self.srcFile, vIDRFrameInter, vResolution, vFrameRate, ABR_VBV, dstFile)

        ffmpegCmd = ffmpegPass1 + cmdJoinSep + ffmpegPass2

        # vBitRate = '1000k'
        #
        # ffmpegCmd  = '%sffmpeg -i %s -v error -c:v libx264 -c:a aac -ar 44100 -ac 2 -b:v %s  %s -s:v %s -r %s %s -y' \
        #              % (self.cmdPath, self.srcFile, vBitRate, vIDRFrameInter,vResolution, vFrameRate, dstFile)
        print ffmpegCmd

        return ffmpegCmd

class MediaXMlParser:
    """"XML format mediainfo parser"""

    def __init__(self):
        self.mediaInfo = {}

    def parser(self, xmlString):
        root = ET.fromstring(xmlString)
        for child in root:
            # print child.tag

            if child.tag == 'format':
                self.getGeneralInfo(child)
            elif child.tag == 'streams':
                subchild = child[0]
                if subchild.tag == "stream" and subchild.attrib['codec_type'] == "video":
                    self.getVideolInfo(subchild)

        for item in self.mediaInfo:
            print item + " : " + self.mediaInfo[item]


        return  self.mediaInfo

    def getGeneralInfo(self, element):
        if element.attrib.has_key('duration'):
            self.mediaInfo.update({'gDuration':element.attrib['duration'].replace(' ', '')})
        if element.attrib.has_key('bit_rate'):
            self.mediaInfo.update({'gBitRate': element.attrib['bit_rate'].replace(' ', '')})

    def getVideolInfo(self, element):

        if element.attrib.has_key('avg_frame_rate'):
            self.mediaInfo.update({'vFrameRate': element.attrib['avg_frame_rate'].replace(' ', '')})
        if element.attrib.has_key('bit_rate'):
            self.mediaInfo.update({'vBitRate': element.attrib['bit_rate'].replace(' ', '')})
        if element.attrib.has_key('width'):
            self.mediaInfo.update({'vWidth': element.attrib['width'].replace(' ', '')})
        if element.attrib.has_key('height'):
            self.mediaInfo.update({'vHeight': element.attrib['height'].replace(' ', '')})

if __name__ == '__main__':
    # if len(sys.argv) < 3:
    #     print "Usage:\n    python transcode.py srcDirectory dstDirectory";
    #     exit();

    obj_fileProcess = FileProcess()
    obj_fileProcess.browserDirectory()
