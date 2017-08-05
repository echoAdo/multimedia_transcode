#encoding=utf-8

import string
import os
import os.path
import sys
import platform
import subprocess
import shutil
import traceback
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
    def __init__(self, logo):
        self.srcFile = ''
        self.cmdPath = ''
        self.logoAdd = logo

        system = platform.system();
        print "Current system is :" + system
        prefix = ''
        if system == "Windows":
            self.cmdPath = os.getcwd() + os.sep + "winFFmpeg" + os.sep
            prefix = '..' + os.sep
        elif system =="Darwin" or system == "Linux":
            pass

        self.srcDirectory = prefix + "input"
        self.failedDirectory = prefix + "failed" + os.sep # transcode failed file dierctory
        if self.logoAdd:
            self.dstDirectory = prefix + "output_withLogo" + os.sep
        else:
            self.dstDirectory = prefix + "output" + os.sep
        if not os.path.exists(self.dstDirectory):
            os.makedirs(self.dstDirectory)
        if not os.path.exists(self.failedDirectory):
            os.makedirs(self.failedDirectory)

        self.ffprobePrefix = "ffprobe -v error -show_entries format -show_entries stream -of xml -i "

    def moveFile(self, src, dst):
        try:
            shutil.move(src, dst)
        except Exception, e:
            print e

    def copyFile(self, src, dst):
        try:
            shutil.copy(src, dst)
        except Exception, e:
            print e
        return None

    def browserDirectory(self):
        list_dirs = os.walk(self.srcDirectory)
        for root, dirs, files in list_dirs:
            for f in files:
                """Strip space character in fileName"""
                newFileName = f.replace(' ', '')
                if f != newFileName:
                    os.rename(os.path.join(root, f), os.path.join(root, newFileName))
                    self.srcFile = os.path.join(root,newFileName)
                else:
                    self.srcFile = os.path.join(root, f)
                print self.srcFile;

                ffprobeCmd = self.cmdPath + self.ffprobePrefix + self.srcFile
                print ffprobeCmd
                xml = runShellCommand(ffprobeCmd)
                if xml is None:
                    self.moveFile(self.srcFile, self.failedDirectory + newFileName)
                    continue

                srcFileInfo = MediaXMlParser().parser(xml)
                if srcFileInfo is None:
                    self.moveFile(self.srcFile, self.failedDirectory + newFileName)
                    continue

                ffmpegCmd = self.buildFFmpegCommand(srcFileInfo)
                if ffmpegCmd is None:
                    continue

                transcodeStatus = runShellCommand(ffmpegCmd)
                if transcodeStatus is None:
                    self.moveFile(self.srcFile, self.failedDirectory + newFileName)

        '''Remove unused file that generate in ffmpeg pass 1'''
        if os.path.exists('ffmpeg2pass-0.log'):
            os.remove('ffmpeg2pass-0.log')
        if os.path.exists('ffmpeg2pass-0.log.mbtree'):
            os.remove('ffmpeg2pass-0.log.mbtree')

    def buildFFmpegCommand(self, info):
        '''buidFFmpegCommand'''

        fileName = self.srcFile.split(os.sep)[-1]
        dstFile = self.dstDirectory + fileName[0:fileName.rfind('.')] + '.mp4'

        ''''File is suitable for streaming, no transcode'''
        if ((not self.logoAdd) and info.get('gFormatName').find('mp4') != -1) and  (info.get('vCodecName') == 'h264') \
            and  (info.get('aCodecName') == 'aac') and (string.atoi(info.get('vBitRate')) <= 800000) \
            and ((string.atoi(info.get('vWidth')) <= 856) or (string.atoi(info.get('vHeight')) <= 480)):

            print "Not transcode, Copying: " + self.srcFile + " ------> " + dstFile
            return  self.copyFile(self.srcFile, dstFile)

        """I frame interval"""
        vDuration = int(string.atof(info.get('gDuration')))
        if vDuration <= 10 : interval = 1
        elif vDuration > 10 and vDuration <= 30 : interval = 3
        else: interval = 0

        if interval > 0: vIDRFrameInter = '-force_key_frames "expr:gte(t,n_forced*%s)"' % interval
        else: vIDRFrameInter = ''

        """ Resolution:
            width/height > 16:10, eg:16:9, 16:10, 5:3 -> 856x480
            other width/height < 16:10                -> 640x480
        """
        width   = info.get('vWidth')
        height  = info.get('vHeight')
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
        ele = info.get('vFrameRate').split('/')
        frameRate = string.atof(ele[0]) / string.atof(ele[1])
        if frameRate > 25: vFrameRate = 25
        else: vFrameRate = round(frameRate,3)

        '''BitRate: TotalBitRate = vBR + aBR'''
        vBR = string.atoi(info.get('vBitRate'))
        if vBR <= 800000:
            ABR_VBV = '-b:v %s -maxrate %s -bufsize %s' % (vBR, vBR, vBR*2)
        else:
            ABR_VBV = '-b:v 800k -maxrate 800k -bufsize 1600k'

        '''audio bitrate'''
        if string.atoi(info.get('aBitRate')) <= 128000: aBR = info.get('aBitRate')
        else: aBR = '128k'

        if self.logoAdd:
            addLogo = '-vf "movie=logo.png [watermark];[in][watermark] overlay=main_w-overlay_w-15:15 [out]"'
        else: addLogo = ''

        system = platform.system();
        if system == "Windows":
            cmdJoinSep = ' NUL & '
        elif system == "Darwin" or system == "Linux":
            cmdJoinSep = " /dev/null && "


        # ffmpegCmd = 'ffmpeg -i backup235.ts -c:v libx264 -b:v 1M -maxrate 1M -bufsize 2M -pass 1 -f mp4 /dev/null -y && ' \
        #             'ffmpeg -i backup235.ts -c:v libx264 -b:v 1M -maxrate 1M -bufsize 2M -pass 2 twopass.mp4 -y'

        ffmpegPass1 = '%sffmpeg -i %s -pass 1 -y -v error -c:v libx264  %s -s:v %s -r %s -c:a aac -ar 44100 -ac 2 -ab %s %s -f mp4 ' \
                      % (self.cmdPath, self.srcFile, vIDRFrameInter, vResolution, vFrameRate, aBR, ABR_VBV)
        ffmpegPass2 = '%sffmpeg -i %s -pass 2 -y -v error -c:v libx264  %s -s:v %s -r %s %s -c:a aac -ar 44100 -ac 2 -ab %s %s %s' \
                      % (self.cmdPath, self.srcFile, vIDRFrameInter, vResolution, vFrameRate, addLogo, aBR, ABR_VBV, dstFile)

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
        # Strip the erorr message generate by ffprobe that out of xml body.
        xmlStart = xmlString.find('<?xml')
        xmlEnd = xmlString.find('</ffprobe>')
        validXml = xmlString[xmlStart:xmlEnd+10]

       # print 'xml --->' ,len(xmlString)
       # xmlHandle = open(str(len(xmlString))+'probe.xml', 'a')
       # xmlHandle.write(xmlString)
       # xmlHandle.write('------------------------------\n')
       # xmlHandle.write(validXml)
       # xmlHandle.close()

        try:
            root = ET.fromstring(validXml)
            for child in root:
                # print child.tag
                if child.tag == 'format':
                    self.getGeneralInfo(child)
                elif child.tag == 'streams':
                    for subchild in child:
                        if subchild.tag == "stream" and subchild.attrib['codec_type'] == "video":
                            self.mediaInfo.update({'hasVideo': '1'})
                            self.getVideolInfo(subchild)
                        if subchild.tag == "stream" and subchild.attrib['codec_type'] == "audio":
                            self.mediaInfo.update({'hasAudio': '1'})
                            self.getAudiolInfo(subchild)
        except Exception, e:
            print e
            print traceback.print_stack()
            return None

        if not self.mediaInfo.has_key('hasVideo') or not self.mediaInfo.has_key('hasAudio'):
            print 'only video or audio'
            return None

        '''Lack of bitrate in audio/video stream, use the value in container'''
        if not self.mediaInfo.has_key('vBitRate') and self.mediaInfo.has_key('gBitRate'):
            bitrate = str(string.atoi(self.mediaInfo.get('gBitRate')) - 128000)
            self.mediaInfo.update({'vBitRate': bitrate})
        if not self.mediaInfo.has_key('aBitRate') and self.mediaInfo.has_key('gBitRate'):
            self.mediaInfo.update({'aBitRate': '128000'})

        print self.mediaInfo

        return  self.mediaInfo

    def getGeneralInfo(self, element):
        if element.attrib.has_key('duration'):
            self.mediaInfo.update({'gDuration':element.attrib['duration'].replace(' ', '')})
        if element.attrib.has_key('bit_rate'):
            self.mediaInfo.update({'gBitRate': element.attrib['bit_rate'].replace(' ', '')})
        if element.attrib.has_key('format_name'):
            self.mediaInfo.update({'gFormatName': element.attrib['format_name'].replace(' ', '')})

    def getVideolInfo(self, element):
        if element.attrib.has_key('codec_name'):
            self.mediaInfo.update({'vCodecName': element.attrib['codec_name'].replace(' ', '')})
        if element.attrib.has_key('avg_frame_rate'):
            self.mediaInfo.update({'vFrameRate': element.attrib['avg_frame_rate'].replace(' ', '')})
        if element.attrib.has_key('bit_rate'):
            self.mediaInfo.update({'vBitRate': element.attrib['bit_rate'].replace(' ', '')})
        if element.attrib.has_key('width'):
            self.mediaInfo.update({'vWidth': element.attrib['width'].replace(' ', '')})
        if element.attrib.has_key('height'):
            self.mediaInfo.update({'vHeight': element.attrib['height'].replace(' ', '')})
        if element.attrib.has_key('profile'):
            self.mediaInfo.update({'vProfile': element.attrib['profile'].replace(' ', '')})

    def getAudiolInfo(self, element):
        if element.attrib.has_key('codec_name'):
            self.mediaInfo.update({'aCodecName': element.attrib['codec_name'].replace(' ', '')})
        if element.attrib.has_key('bit_rate'):
            self.mediaInfo.update({'aBitRate': element.attrib['bit_rate'].replace(' ', '')})
        if element.attrib.has_key('sample_rate'):
            self.mediaInfo.update({'aSampleRate': element.attrib['sample_rate'].replace(' ', '')})
        if element.attrib.has_key('channels'):
            self.mediaInfo.update({'aChannels': element.attrib['channels'].replace(' ', '')})
        if element.attrib.has_key('profile'):
            self.mediaInfo.update({'aProfile': element.attrib['profile'].replace(' ', '')})

if __name__ == '__main__':
    # if len(sys.argv) < 3:
    #     print "Usage:\n    python transcode.py srcDirectory dstDirectory";
    #     exit();

    if len(sys.argv) == 2:
        logo = sys.argv[1] != '0' and True or False
    else:
        logo = False

    obj_fileProcess = FileProcess(logo)
    obj_fileProcess.browserDirectory()
